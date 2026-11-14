"""Minimaler SSH-Server mit paramiko, um das Ausschalten echt zu testen."""

import socket
import threading

import paramiko


class _Handler(paramiko.ServerInterface):
    def __init__(self, server):
        self.server = server
        self.event = threading.Event()

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def get_allowed_auths(self, username):
        return "password,publickey"

    def check_auth_password(self, username, password):
        if username == self.server.username and password == self.server.password:
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def check_auth_publickey(self, username, key):
        if username == self.server.username and self.server.allowed_key is not None and (
            key.get_base64() == self.server.allowed_key.get_base64()
        ):
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def check_channel_exec_request(self, channel, command):
        self.server.commands.append(command.decode())
        def reply():
            threading.Event().wait(0.1)
            channel.sendall(b"bye\n")
            channel.send_exit_status(self.server.exit_code)
            channel.close()
        threading.Thread(target=reply, daemon=True).start()
        return True


class FakeSSHServer:
    def __init__(self, username="user", password="pw", allowed_key=None, exit_code=0):
        self.username = username
        self.password = password
        self.allowed_key = allowed_key
        self.exit_code = exit_code
        self.commands: list[str] = []
        self.host_key = paramiko.RSAKey.generate(2048)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self._stop = False
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        t = paramiko.Transport(conn)
        t.add_server_key(self.host_key)
        try:
            t.start_server(server=_Handler(self))
            chan = t.accept(5)
            if chan is not None:
                while chan.active and not chan.closed:
                    threading.Event().wait(0.05)
        except Exception:  # noqa: BLE001
            pass
        finally:
            threading.Event().wait(0.2)
            t.close()

    def close(self):
        self._stop = True
        self.sock.close()
