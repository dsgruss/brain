from dataclasses import dataclass


@dataclass
class HostModule:
    uuid: str
    address: str
    port: int
    local_address: str
