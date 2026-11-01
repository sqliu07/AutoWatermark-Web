"""Honor one forwarding hop only when the socket peer is explicitly trusted."""

from ipaddress import ip_address, ip_network

from werkzeug.middleware.proxy_fix import ProxyFix


class TrustedProxyFix:
    def __init__(self, app, networks):
        self.app = app
        self.networks = tuple(ip_network(value.strip()) for value in networks)
        self.proxy_app = ProxyFix(app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0)

    def __call__(self, environ, start_response):
        try:
            peer = ip_address(environ.get("REMOTE_ADDR", ""))
        except ValueError:
            return self.app(environ, start_response)
        if any(peer in network for network in self.networks):
            return self.proxy_app(environ, start_response)
        return self.app(environ, start_response)
