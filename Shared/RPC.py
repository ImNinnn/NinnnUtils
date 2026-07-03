def start_local_rpc_worker():
    global local_rpc_thread
    if not RPC_CLIENT_ID:
        return
    if local_rpc_thread is not None and local_rpc_thread.is_alive():
        return
    local_rpc_thread = None

    def worker():
        global local_rpc, local_rpc_thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = None
        start_timestamp = time.time()

        try:
            client = Presence(RPC_CLIENT_ID, loop=loop)
            client.connect()
            local_rpc = client

            while not local_rpc_stop_event.is_set():
                try:
                    activity_text = local_rpc_queue.get(timeout=1)
                except queue.Empty:
                    continue

                if activity_text is None:
                    break

                try:
                    client.update(activity_type=ActivityType.WATCHING, 
                                  name=f"{bot.user}",
                                  state=activity_text, 
                                  details=f"Running {bot.user.name} bot",
                                  start=start_timestamp,
                                  buttons=[{"label": "Git", "url": "https://github.com/ImNinnn/NinnnUtils"},{"label": "Support Server", "url": "https://discord.gg/FSBPvc9zqY"}]
                    )
                except Exception as e:
                    print(f"Local RPC sync failed: {e}")
                    break
        except Exception as e:
            print(f"Local RPC sync failed: {e}")
        finally:
            try:
                if client is not None:
                    client.close()
            except Exception:
                pass
            local_rpc = None
            local_rpc_thread = None
            loop.close()

    local_rpc_stop_event.clear()
    local_rpc_thread = threading.Thread(target=worker, name="LocalRPC", daemon=True)
    local_rpc_thread.start()


def sync_local_rpc(activity_text: str):
    if not RPC_CLIENT_ID:
        return

    start_local_rpc_worker()

    try:
        while not local_rpc_queue.empty():
            local_rpc_queue.get_nowait()
    except queue.Empty:
        pass

    try:
        local_rpc_queue.put_nowait(activity_text)
    except queue.Full:
        pass


def close_local_rpc():
    global local_rpc_thread

    local_rpc_stop_event.set()
    try:
        while not local_rpc_queue.empty():
            local_rpc_queue.get_nowait()
    except queue.Empty:
        pass

    try:
        local_rpc_queue.put_nowait(None)
    except queue.Full:
        pass

    if local_rpc_thread is not None:
        local_rpc_thread.join(timeout=5)
        local_rpc_thread = None

