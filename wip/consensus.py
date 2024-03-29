import asyncio
import json
import netifaces
import socket
import threading

from enum import Enum


class PatchState(Enum):
    # Global state possibilities
    IDLE = 0  # No buttons pushed across all modules
    PATCH_ENABLED = 1  # One single button pushed
    PATCH_TOGGLED = 2  # Two buttons pushed, consisting of an input and output
    BLOCKED = 3  # Three or more buttons pushed or two of the same type


class ConsensusProtocol(asyncio.DatagramProtocol):

    polling_active = False
    polling_leader = ""
    polling_sequence_number = 0
    poll_responses = []

    def __init__(self, uuid, port) -> None:
        self.uuid = uuid
        self.port = port
        self.sequence_number = 0
        self.broadcast_addrs = []

        for interface in netifaces.interfaces():
            interfaces_details = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in interfaces_details:
                for detail in interfaces_details[netifaces.AF_INET]:
                    if detail["addr"] != "127.0.0.1":
                        self.broadcast_addrs.append((detail["broadcast"], port))

        self.sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 2)
        self.sock.bind(("", self.port))

        super().__init__()

    def datagram_send(self, json_msg):
        payload = bytes(json.dumps(json_msg), "utf8")
        for addr in self.broadcast_addrs:
            self.sock.sendto(payload, addr)

    def start_poll(self):
        self.sequence_number += 1
        self.poll_responses = []
        self.polling_active = True
        self.polling_sequence_number = self.sequence_number
        self.polling_leader = self.uuid
        self.datagram_send(
            {
                "message": "POLL",
                "uuid": self.uuid,
                "sequence_number": self._sequence_number,
            }
        )

    def datagram_received(self, data: bytes, addr) -> None:
        try:
            response = json.loads(data)
        except json.JSONDecodeError:
            return
        if (
            "message" not in response
            or "uuid" not in response
            or response["uuid"] == self.uuid
        ):
            return

        if not self.polling_active:
            if response["message"] == "POLL":
                self.polling_active = True
                self.polling_leader = response["uuid"]
                self.polling_sequence_number = response["sequence_number"]
                self.datagram_send(
                    {
                        "message": "OFFER",
                        "uuid": self.uuid,
                        "leader_uuid": self.polling_leader,
                        "sequence_number": self.polling_sequence_number,
                        "local_state": self._local_state,
                    }
                )
        else:
            if response["message"] == "POLL":
                # Polling conflict detected
                if self.polling_leader == self.uuid:
                    if self.uuid < response["uuid"]:
                        # We have the lower id, so we take priority
                        self.start_poll()
                    else:
                        # Defer to the more recent poll
                        self.polling_active = False
                        self.datagram_received(data, addr)
                else:
                    if response["uuid"] <= self.polling_leader:
                        # Respond to the new poll only if it takes priority
                        self.polling_active = False
                        self.datagram_received(data, addr)
                    else:
                        # Drop polls that come from a higher id
                        return
            elif response["message"] == "OFFER":
                # Only accept offered data if we are the leader and the
                # sequence is correct
                if (
                    self.polling_leader == self.uuid
                    and response["leader_uuid"] == self.uuid
                    and response["sequence_number"] == self.polling_sequence_number
                ):
                    self.poll_responses.extend(response["local_state"])
            elif response["message"] == "QUORUM":
                self.state = response["global_state"]


class Consensus:
    # This class manages the global state across the synthesizer in terms of whether a patch event
    # is ongoing or not. For now, it runs in another thread and talks via a broadcast.
    #
    # Consensus protocol:
    # - On local state change, broadcast to all other modules to do a state check-in
    # - If found to have contentious broadcasts, defer to node with lowest id and increment sequence
    #   for another round
    # - All other nodes respond to broadcast with local state
    # - After a short timeout or if total patching > 3, broadcast results of global state
    # Until global state is established, changes to the local state do not propagate
    # Only PATCH_TOGGLED is a non-cosmetic effect, which happens once when the state is changed

    consensus_port = 39826
    state = PatchState.IDLE
    _sequence_number = 0
    _local_state = []
    _local_state_changed = False
    _network_interfaces = []

    def __init__(self, state_update_callback, uuid):
        self.state_update_callback = state_update_callback
        self.uuid = str(uuid)

        print(f"Listening for polls on broadcast port {self.consensus_port}")

        self._sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 2)

        self._sock.bind(("", self.consensus_port))
        self._sock.settimeout(1)

        print(self._network_interfaces)
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        # Thread that responds to and create consensus broadcasts

        while True:
            while self._local_state_changed:
                print(f"Starting new consensus evaluation {self._sequence_number}")
                self.send(
                    {
                        "message": "POLL",
                        "uuid": self.uuid,
                        "sequence_number": self._sequence_number,
                    }
                )
                try:
                    response = {"message": None}
                    global_state = self._local_state.copy()
                    seen = set()
                    while True:
                        msg, addr = self._sock.recvfrom(1024)
                        print(msg, addr)
                        response = json.loads(msg)
                        if (
                            "message" not in response
                            or "uuid" not in response
                            or response["uuid"] == self.uuid
                        ):
                            continue
                        if response["message"] == "POLL":
                            break
                        if response["message"] == "OFFER":
                            if (
                                response["sequence_number"] != self._sequence_number
                                or response["leader_uuid"] != self.uuid
                                or response["uuid"] in seen
                            ):
                                continue
                            print(global_state, response["local_state"])
                            global_state += response["local_state"]
                            seen.add(response["uuid"])
                    if response["message"] == "POLL":
                        if self.uuid > response["uuid"]:
                            self._local_state_changed = False
                            break
                        else:
                            self._sequence_number += 1
                            continue
                except socket.timeout:
                    pass
                self._local_state_changed = False
                self.state = PatchState(min(3, len(global_state)))
                self.send(
                    {
                        "message": "QUORUM",
                        "uuid": self.uuid,
                        "sequence_number": self._sequence_number,
                        "global_state": self.state.name,
                    }
                )
                self._sequence_number += 1
            try:
                msg, addr = self._sock.recvfrom(1024)
                print(msg, addr)
                response = json.loads(msg)
                if (
                    "message" not in response
                    or "uuid" not in response
                    or response["uuid"] == self.uuid
                ):
                    continue
                if response["message"] == "POLL":
                    self.send(
                        {
                            "message": "OFFER",
                            "uuid": self.uuid,
                            "leader_uuid": response["uuid"],
                            "sequence_number": response["sequence_number"],
                            "local_state": self._local_state,
                        }
                    )
                elif response["message"] == "QUORUM":
                    self.state = response["global_state"]
            except socket.timeout:
                print(self.state, self._local_state, self._local_state_changed)

    def update(self, local_state):
        # Updates the local state and triggers a global check-in
        self._local_state = local_state
        self._local_state_changed = True
        print(self._local_state, self._local_state_changed)
