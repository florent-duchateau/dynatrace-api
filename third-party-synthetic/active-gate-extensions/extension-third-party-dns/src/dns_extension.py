from datetime import datetime
import logging

from dns import resolver

from ruxit.api.base_plugin import RemoteBasePlugin
from dynatrace import Dynatrace
from dynatrace.environment_v1.synthetic_third_party import SYNTHETIC_EVENT_TYPE_OUTAGE

log = logging.getLogger(__name__)


class DNSExtension(RemoteBasePlugin):
    def initialize(self, **kwargs):
        # The Dynatrace API client
        self.dt_client = Dynatrace(
            self.config.get("api_url"), self.config.get("api_token"), log=log, proxies=self.build_proxy_url()
        )
        self.executions = 0

    def build_proxy_url(self):
        proxy_address = self.config.get("proxy_address")
        proxy_username = self.config.get("proxy_username")
        proxy_password = self.config.get("proxy_password")

        if proxy_address:
            protocol, address = proxy_address.split("://")
            proxy_url = f"{protocol}://"
            if proxy_username:
                proxy_url += proxy_username
            if proxy_password:
                proxy_url += f":{proxy_password}"
            proxy_url += f"@{address}"
            return {"https": proxy_url}

        return {}

    def query(self, **kwargs) -> None:

        log.setLevel(self.config.get("log_level"))
        dns_server = self.config.get("dns_server")
        host = self.config.get("host")

        step_title = f"{host} (DNS: {dns_server})"
        test_title = self.config.get("test_name") if self.config.get("test_name") else step_title
        location = self.config.get("test_location") if self.config.get("test_location") else "ActiveGate"
        location_id = location.replace(" ", "_").lower()
        frequency = int(self.config.get("frequency")) if self.config.get("frequency") else 15

        if self.executions % frequency == 0:
            success, response_time = test_dns(dns_server, host)
            log.info(f"DNS test, DNS server: {dns_server}, host: {host}, success: {success}, time: {response_time} ")

            self.dt_client.report_simple_thirdparty_synthetic_test(
                engine_name="DNS",
                timestamp=datetime.now(),
                location_id=location_id,
                location_name=location,
                test_id=self.activation.entity_id,
                test_title=test_title,
                step_title=step_title,
                schedule_interval=frequency * 60,
                success=success,
                response_time=response_time,
                edit_link=f"#settings/customextension;id={self.plugin_info.name}",
                icon_url="https://raw.githubusercontent.com/Dynatrace/dynatrace-api/master/third-party-synthetic/active-gate-extensions/extension-third-party-dns/dns.png",
            )

            self.dt_client.report_simple_thirdparty_synthetic_test_event(
                test_id=self.activation.entity_id,
                name=f"DNS lookup failed for {step_title}",
                location_id=location_id,
                timestamp=datetime.now(),
                state="open" if not success else "resolved",
                event_type=SYNTHETIC_EVENT_TYPE_OUTAGE,
                reason=f"DNS lookup failed for {step_title}",
                engine_name="DNS",
            )

        self.executions += 1


def test_dns(dns_server: str, host: str) -> (bool, int):
    res = resolver.Resolver(configure=False)
    res.nameservers = [dns_server]
    res.lifetime = res.timeout = 2

    start = datetime.now()
    try:
        res.query(host, "A")
    except Exception as e:
        log.error(f"Failed executing the DNS test: {e}")
        return False, int((datetime.now() - start).total_seconds() * 1000)

    return True, int((datetime.now() - start).total_seconds() * 1000)
