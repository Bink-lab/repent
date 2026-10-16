try:
    from ytqueue import MusicPlayer, Resolver, ResolverConfig
    from ytqueue.discord import DiscordPlayer
    from ytqueue.cookie_sync import CookieSyncServer
    YTQUEUE_AVAILABLE = True
except ImportError as e:
    YTQUEUE_AVAILABLE = False
    print(f"[WARNING] ytqueue is not installed - music commands are disabled. Run: pip install ytqueue ({e})")

try:
    import numpy as _np
    import sounddevice as _sd
    LOCAL_AUDIO_AVAILABLE = True
except Exception as e:  # sounddevice raises OSError when PortAudio itself is missing
    LOCAL_AUDIO_AVAILABLE = False
    print(f"[WARNING] sounddevice/numpy unavailable - music can't play on this PC's speakers. Run: pip install sounddevice numpy ({e})")

MUSIC_COOKIES_FILE = str(DATA_DIR / "cookies.txt")
LOCAL_MUSIC_KEY = "local"
_music_cookie_server = None
_music_resolver = None
_music_players = {}
_music_last_channel = {}
_local_player = None

if YTQUEUE_AVAILABLE:
    try:
        _music_cookie_server = CookieSyncServer(cookies_file=MUSIC_COOKIES_FILE)
        _music_cookie_server.start()
    except Exception as e:
        print(f"[WARNING] Could not start the music cookie-sync server: {e}")
        _music_cookie_server = None

    _music_resolver = Resolver(ResolverConfig(
        cookies_file=MUSIC_COOKIES_FILE,
        on_cookie_error=_music_cookie_server.request_refresh_and_wait if _music_cookie_server else None,
    ))

def _format_duration(seconds):
    if not seconds:
        return "Unknown"
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    mins, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"

def _local_output_devices():
    # WASAPI has full device names (MME cuts them at 31 chars) and working blocking writes (DirectSound's return instantly)
    hostapis = _sd.query_hostapis()
    hostapi = next((i for i, h in enumerate(hostapis) if h['name'] == 'Windows WASAPI'), None)
    devices = []
    for index, device in enumerate(_sd.query_devices()):
        if device['max_output_channels'] < 1:
            continue
        if hostapi is not None and device['hostapi'] != hostapi:
            continue
        devices.append((index, device['name']))
    default = hostapis[hostapi]['default_output_device'] if hostapi is not None else None
    return devices, default

def _resolve_output_device(name):
    devices, default = _local_output_devices()
    if name:
        for index, device_name in devices:
            if device_name == name:
                return index
        for index, device_name in devices:
            if name.lower() in device_name.lower():
                return index
        print(f"[WARNING] Music output device '{name}' wasn't found, using the Windows default instead.")
    return default

class LocalSpeakerPlayer:
    """Plays a ytqueue MusicPlayer through this PC's speakers instead of a voice channel.
    Mirrors the bits of DiscordPlayer/VoiceClient the music commands use."""

    def __init__(self, core):
        self.core = core
        self.volume = 1.0
        self.device = None
        self.on_playback_error = None
        self._active = False
        self._halted = False
        self._stop = threading.Event()
        self._loop = None
        self._advance_lock = asyncio.Lock()
        self.core.bind_sink(self._play_source)

    async def enqueue_url_or_query(self, text):
        return await self.core.enqueue_url_or_query(text)

    def is_playing(self):
        return self._active

    def is_paused(self):
        return False

    async def play_next(self):
        self._halted = False
        return await self._advance()

    def stop(self):
        # Ends the current track; the next one starts unless halt() was called
        self._stop.set()

    def halt(self):
        self._halted = True
        self.stop()

    async def _advance(self):
        async with self._advance_lock:
            if self._halted or self._active:
                return None
            self._loop = asyncio.get_running_loop()
            return await self.core.play_next()

    def _play_source(self, source):
        self._stop = threading.Event()
        self._active = True
        threading.Thread(target=self._run, args=(source, self._stop), daemon=True, name="music-local-output").start()

    def _run(self, source, stop):
        error = None
        options = self.core.ffmpeg_options
        try:
            device = _resolve_output_device(self.device)
            # auto_convert lets Windows resample, so 48kHz plays on 44.1kHz speakers too
            extra = _sd.WasapiSettings(auto_convert=True) if _sd.query_hostapis(_sd.query_devices(device)['hostapi'])['name'] == 'Windows WASAPI' else None
            with _sd.RawOutputStream(samplerate=options.sample_rate, channels=options.channels, dtype="int16",
                                     device=device, extra_settings=extra) as stream:
                while not stop.is_set():
                    frame = source.read()
                    if not frame:
                        break
                    volume = self.volume
                    if volume != 1.0:
                        samples = _np.frombuffer(frame, dtype=_np.int16).astype(_np.float32) * volume
                        frame = _np.clip(samples, -32768, 32767).astype(_np.int16).tobytes()
                    stream.write(frame)
                if stop.is_set():
                    stream.abort()  # drop buffered audio so skips are instant
        except Exception as e:
            # ffmpeg failures just end the stream, so anything raised here is the audio device itself
            error = e
            self._halted = True
        finally:
            source.cleanup()
        self.core.on_track_finished(error)
        self._active = False
        if self._loop is None:
            return
        if error is not None and self.on_playback_error is not None:
            asyncio.run_coroutine_threadsafe(self.on_playback_error(error), self._loop)
        elif not self._halted:
            asyncio.run_coroutine_threadsafe(self._advance(), self._loop)

def _setup_music_player(player, key):
    async def _on_track_started(track):
        channel = _music_last_channel.get(key)
        if channel is None:
            return
        body = f"{track.title}\nDuration: {_format_duration(track.duration)}"
        await panelmaker(channel, "Now Playing", body, "mplay")

    async def _on_track_skipped(track):
        channel = _music_last_channel.get(key)
        if channel is None:
            return
        await panelmaker(channel, "Track Skipped", f"Couldn't load '{track.title}', skipping.", "mplay")

    player.core.on_track_started = _on_track_started
    player.core.on_track_skipped_load_failure = _on_track_skipped
    default_volume = config_get('music_volume')
    if isinstance(default_volume, (int, float)):
        player.volume = max(0, min(200, default_volume)) / 100
    default_autoplay = config_get('music_autoplay')
    if default_autoplay is not None:
        player.core.queue.autoplay_enabled = bool(default_autoplay)

def get_music_player(guild_id):
    player = _music_players.get(guild_id)
    if player is None:
        player = DiscordPlayer(core=MusicPlayer(resolver=_music_resolver))
        _setup_music_player(player, guild_id)
        _music_players[guild_id] = player
    return player

def get_local_player():
    global _local_player
    if _local_player is None:
        _local_player = LocalSpeakerPlayer(core=MusicPlayer(resolver=_music_resolver))
        _setup_music_player(_local_player, LOCAL_MUSIC_KEY)

        async def _on_playback_error(error):
            channel = _music_last_channel.get(LOCAL_MUSIC_KEY)
            if channel is not None:
                await panelmaker(channel, "Error", f"Couldn't play on your speakers: {error}\nPick another output with {config_get('prefix')}mdevice.", "ERROR")

        _local_player.on_playback_error = _on_playback_error
    _local_player.device = config_get('music_device') or None
    return _local_player

def music_plays_locally():
    return bool(config_get('music_local'))

def _music_player_for(ctx):
    # The player a command acts on: the speaker player in local mode, otherwise this server's voice player
    if music_plays_locally():
        return get_local_player()
    if ctx.guild is None:
        return None
    return get_music_player(ctx.guild.id)

def _existing_music_player(ctx):
    if music_plays_locally():
        return _local_player
    return _music_players.get(ctx.guild.id) if ctx.guild else None

async def ensure_music_voice(ctx):
    if ctx.guild is None:
        return None, "This command only works inside a server."
    if not ctx.author.voice or not ctx.author.voice.channel:
        if ctx.author.id == Repent.user.id:
            return None, ("You need to be in a voice channel first. To listen from another account while repent "
                          "plays, run repent on an alt and add your main's user ID under Settings → Music. "
                          f"Or use {config_get('prefix')}moutput speakers to play on this PC instead.")
        return None, "You need to be in a voice channel first."
    vc = ctx.guild.voice_client
    try:
        if vc is None:
            vc = await ctx.author.voice.channel.connect()
        elif vc.channel.id != ctx.author.voice.channel.id:
            await vc.move_to(ctx.author.voice.channel)
    except Exception as e:
        return None, f"Couldn't connect to voice: {e}"
    return vc, None

@Repent.command(aliases=['mp'], description=f"Plays a song from YouTube (URL or search query) in your voice channel, or on your PC's speakers with moutput. \nUsage: {config_get('prefix')}mplay <query/url>", help="music")
async def mplay(ctx, *, query: str):
    if not YTQUEUE_AVAILABLE:
        await panelmaker(ctx, "Error", "ytqueue isn't installed. Run `pip install ytqueue` and restart.", "ERROR")
        return
    if music_plays_locally():
        if not LOCAL_AUDIO_AVAILABLE:
            await panelmaker(ctx, "Error", "Speaker playback needs sounddevice. Run `pip install sounddevice numpy` and restart.", "ERROR")
            return
        player = vc = get_local_player()
        key = LOCAL_MUSIC_KEY
    else:
        vc, error = await ensure_music_voice(ctx)
        if error:
            await panelmaker(ctx, "Error", error, "ERROR")
            return
        player = get_music_player(ctx.guild.id)
        key = ctx.guild.id
    _music_last_channel[key] = ctx.channel
    tracks = await player.enqueue_url_or_query(query)
    if not tracks:
        await panelmaker(ctx, "Error", f"Couldn't find anything for '{query}'.", "ERROR")
        return
    was_idle = not (vc.is_playing() or vc.is_paused())
    if player is _local_player:
        await player.play_next()
    else:
        await player.play_next(ctx, vc)
    if not was_idle:
        names = "\n".join(f"- {t.title}" for t in tracks[:5])
        await panelmaker(ctx, "Added to Queue", names, "mplay")

@Repent.command(description=f"Skips the currently playing song. \nUsage: {config_get('prefix')}mskip", help="music")
async def mskip(ctx):
    if music_plays_locally():
        vc = _local_player
    else:
        vc = ctx.guild.voice_client if ctx.guild else None
    if vc is None or not (vc.is_playing() or vc.is_paused()):
        await panelmaker(ctx, "Error", "Nothing is playing.", "ERROR")
        return
    vc.stop()
    await panelmaker(ctx, "Skipped", "Skipped to the next track.", "mskip")

@Repent.command(aliases=['mleave', 'mdc'], description=f"Stops playback, clears the queue, and leaves the voice channel. \nUsage: {config_get('prefix')}mstop", help="music")
async def mstop(ctx):
    if music_plays_locally():
        if _local_player is None or not (_local_player.is_playing() or _local_player.core.queue.tracks):
            await panelmaker(ctx, "Error", "Nothing is playing.", "ERROR")
            return
        _local_player.core.queue.clear()
        _local_player.core.queue.loop_enabled = False
        _local_player.halt()
        await panelmaker(ctx, "Stopped", "Stopped playback on your speakers.", "mstop")
        return
    vc = ctx.guild.voice_client if ctx.guild else None
    if vc is None:
        await panelmaker(ctx, "Error", "Not connected to a voice channel.", "ERROR")
        return
    player = _music_players.get(ctx.guild.id)
    if player:
        player.core.queue.clear()
        player.core.queue.loop_enabled = False
    if vc.is_playing() or vc.is_paused():
        vc.stop()
    await vc.disconnect()
    await panelmaker(ctx, "Stopped", "Stopped playback and left the voice channel.", "mstop")

@Repent.command(description=f"Shows the current music queue. \nUsage: {config_get('prefix')}mqueue", help="music")
async def mqueue(ctx):
    player = _existing_music_player(ctx)
    if player is None or (not player.core.queue.current and not player.core.queue.tracks):
        await panelmaker(ctx, "Queue", "Nothing is queued.", "mqueue")
        return
    body = ""
    if player.core.queue.current:
        body += f"Now Playing: {player.core.queue.current.title}\n\n"
    if player.core.queue.tracks:
        upcoming = "\n".join(f"{i+1}. {t.title}" for i, t in enumerate(list(player.core.queue.tracks)[:10]))
        body += f"Up Next:\n{upcoming}"
    else:
        body += "Nothing else queued."
    await panelmaker(ctx, "Queue", body, "mqueue")

@Repent.command(aliases=['mnp'], description=f"Shows the currently playing song. \nUsage: {config_get('prefix')}mnowplaying", help="music")
async def mnowplaying(ctx):
    player = _existing_music_player(ctx)
    if player is None or not player.core.queue.current:
        await panelmaker(ctx, "Now Playing", "Nothing is playing.", "mnowplaying")
        return
    track = player.core.queue.current
    elapsed = int(player.core.queue.elapsed() or 0)
    body = f"{track.title}\nElapsed: {_format_duration(elapsed)} / {_format_duration(track.duration)}"
    await panelmaker(ctx, "Now Playing", body, "mnowplaying")

@Repent.command(description=f"Toggles looping the current track. \nUsage: {config_get('prefix')}mloop [true/false]", help="music")
async def mloop(ctx, state: bool = None):
    player = _music_player_for(ctx)
    if player is None:
        await panelmaker(ctx, "Error", "This command only works inside a server.", "ERROR")
        return
    if state is None:
        state = not player.core.queue.loop_enabled
    player.core.queue.loop_enabled = state
    await panelmaker(ctx, "Loop", f"Loop {'enabled' if state else 'disabled'}.", "mloop")

@Repent.command(description=f"Toggles autoplay (queues similar songs once the queue runs out). \nUsage: {config_get('prefix')}mautoplay [true/false]", help="music")
async def mautoplay(ctx, state: bool = None):
    player = _music_player_for(ctx)
    if player is None:
        await panelmaker(ctx, "Error", "This command only works inside a server.", "ERROR")
        return
    if state is None:
        state = not player.core.queue.autoplay_enabled
    player.core.queue.autoplay_enabled = state
    await panelmaker(ctx, "Autoplay", f"Autoplay {'enabled' if state else 'disabled'}.", "mautoplay")

@Repent.command(description=f"Sets the music playback volume (0-200). \nUsage: {config_get('prefix')}mvolume <0-200>", help="music")
async def mvolume(ctx, percent: int):
    player = _music_player_for(ctx)
    if player is None:
        await panelmaker(ctx, "Error", "This command only works inside a server.", "ERROR")
        return
    percent = max(0, min(200, percent))
    player.volume = percent / 100
    if player is not _local_player:
        vc = ctx.guild.voice_client
        if vc is not None and vc.source is not None:
            vc.source.volume = percent / 100
    await panelmaker(ctx, "Volume", f"Volume set to {percent}%.", "mvolume")

@Repent.command(aliases=['mlocal'], description=f"Switches music between your PC's speakers and voice channels. \nUsage: {config_get('prefix')}moutput [speakers/vc]", help="music")
async def moutput(ctx, mode: str = None):
    if mode is None:
        local = not music_plays_locally()
    elif mode.lower() in ("speakers", "speaker", "local", "pc"):
        local = True
    elif mode.lower() in ("vc", "voice", "discord"):
        local = False
    else:
        await panelmaker(ctx, "Error", "Pick either `speakers` or `vc`.", "ERROR")
        return
    if local and not LOCAL_AUDIO_AVAILABLE:
        await panelmaker(ctx, "Error", "Speaker playback needs sounddevice. Run `pip install sounddevice numpy` and restart.", "ERROR")
        return
    config_edit('music_local', local)
    if not local and _local_player is not None:
        _local_player.core.queue.clear()
        _local_player.halt()
    if local:
        device = config_get('music_device') or "Windows default"
        body = f"Music now plays on this PC's speakers ({device}). Change the output with {config_get('prefix')}mdevice."
    else:
        body = "Music now plays in your voice channel."
    await panelmaker(ctx, "Music Output", body, "moutput")

@Repent.command(aliases=['mspeakers', 'mdevices'], description=f"Lists your PC's speakers or picks which one music plays on. \nUsage: {config_get('prefix')}mdevice [number/name/default]", help="music")
async def mdevice(ctx, *, choice: str = None):
    if not LOCAL_AUDIO_AVAILABLE:
        await panelmaker(ctx, "Error", "Speaker playback needs sounddevice. Run `pip install sounddevice numpy` and restart.", "ERROR")
        return
    if _local_player is None or not _local_player.is_playing():
        # PortAudio only sees devices that existed when it started; re-scan so newly plugged speakers show up
        _sd._terminate()
        _sd._initialize()
    devices, _ = _local_output_devices()
    current = config_get('music_device')
    if choice is None:
        lines = [f"{'> ' if not current else ''}0. Windows default"]
        lines += [f"{'> ' if name == current else ''}{i}. {name}" for i, (_, name) in enumerate(devices, start=1)]
        body = "\n".join(lines) + f"\n\nPick one with {config_get('prefix')}mdevice <number>"
        await panelmaker(ctx, "Speakers", body, "mdevice")
        return
    if choice.strip().lower() in ("0", "default"):
        picked = None
    elif choice.strip().isdigit() and 1 <= int(choice) <= len(devices):
        picked = devices[int(choice) - 1][1]
    else:
        matches = [name for _, name in devices if choice.lower() in name.lower()]
        if not matches:
            await panelmaker(ctx, "Error", f"No speakers match '{choice}'. Run {config_get('prefix')}mdevice to see the list.", "ERROR")
            return
        picked = matches[0]
    config_edit('music_device', picked)
    if _local_player is not None:
        _local_player.device = picked
    note = " Takes effect from the next song." if _local_player is not None and _local_player.is_playing() else ""
    await panelmaker(ctx, "Speakers", f"Music will play on: {picked or 'Windows default'}.{note}", "mdevice")
