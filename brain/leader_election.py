# In the initial implementation, each module would simply broadcast to all modules whenever their
# local state changed, and if two modules detected the patch toggle state, then they would enable
# the connection on either end. However, this could potentially result in the condition that one
# button is released while the update events are still in flight. Therefore, one module would think
# that it is patched to another while that module is unaware of the connection. Additionally, if a
# module goes offline during a patching event, the released button update would not be sent and the
# system as a whole would be stuck in an erroneous state.
#
# This module is an implementation of the "leader election" component of Raft, whereby one elected
# module takes on the responsibility of keeping track of the global patch state and informing all
# the other modules. Rather than maintaining a full log of state, the leader module takes the local
# state with each heartbeat and calculates the needed global conditions.
#
# This can be expanded to keep track of all current patch connections made in the future, if
# required.

from dataclasses import dataclass
from random import randrange
from time import perf_counter_ns
from brain.interfaces import HeldInputJack, HeldOutputJack, LocalState, PatchState
from brain.parsers import Message
from enum import Enum
from typing import Final, Optional, Set


class Roles(Enum):
    FOLLOWER = "FOLLOWER"
    CANDIDATE = "CANDIDATE"
    LEADER = "LEADER"


@dataclass
class Heartbeat(Message):
    term: int


@dataclass
class HeartbeatResponse(Message):
    term: int
    success: bool
    state: Optional[LocalState]


@dataclass
class GlobalStateUpdate(Message):
    patch_state: PatchState
    input: Optional[HeldInputJack]
    output: Optional[HeldOutputJack]


@dataclass
class RequestVote(Message):
    term: int


@dataclass
class RequestVoteResponse(Message):
    term: int
    voted_for: str
    vote_granted: bool


class LeaderElection:
    current_term = 0
    voted_for = None
    role = Roles.FOLLOWER

    election_timeout_interval: Final = (150, 300)  # ms
    heartbeat_interval: Final = 50  # ms
    response_timeout: Final = 50  # ms

    def __init__(self, id, patch_server) -> None:
        self.id = id
        self.patch_server = patch_server
        self.seen_hosts: Set[str] = set()
        self.local_state = LocalState([], [])
        self.reset_election_timer()

    def time_ms(self):
        return perf_counter_ns() // 1000000

    def reset_election_timer(self):
        self.election_time = self.time_ms()

    def reset_heartbeat_timer(self):
        self.heartbeat_time = self.time_ms()

    def election_timer_elapsed(self):
        return (self.time_ms() - self.election_time) > randrange(
            *self.election_timeout_interval
        )

    def heartbeat_timer_elapsed(self):
        return (self.time_ms() - self.heartbeat_time) > self.response_timeout

    def update(self, message: Message):

        if message is not None:
            self.seen_hosts.add(message.uuid)
            if message.uuid == self.id:
                return

        if isinstance(message, Heartbeat):
            if message.term < self.current_term:
                self.patch_server.message_send(
                    HeartbeatResponse(self.id, self.current_term, False, None)
                )
            else:
                if message.term > self.current_term:
                    self.current_term = message.term
                    self.role = Roles.FOLLOWER
                    self.voted_for = message.uuid
                self.reset_election_timer()
                self.patch_server.message_send(
                    HeartbeatResponse(
                        self.id, self.current_term, True, self.local_state
                    )
                )

        if isinstance(message, RequestVote):
            if message.term < self.current_term:
                self.patch_server.message_send(
                    RequestVoteResponse(self.id, self.current_term, message.uuid, False)
                )
            else:
                if message.term > self.current_term:
                    self.current_term = message.term
                    self.role = Roles.FOLLOWER
                    self.voted_for = None
                if self.voted_for is None or self.voted_for == message.uuid:
                    self.reset_election_timer()
                    self.patch_server.message_send(
                        RequestVoteResponse(
                            self.id, self.current_term, message.uuid, True
                        )
                    )

        if self.role == Roles.FOLLOWER and self.election_timer_elapsed():
            self.role = Roles.CANDIDATE
            self.current_term += 1
            self.voted_for = self.id
            self.seen_hosts = set()
            self.votes_got = 1
            self.reset_election_timer()
            self.reset_heartbeat_timer()
            self.patch_server.message_send(RequestVote(self.id, self.current_term))

        if self.role == Roles.CANDIDATE:
            if isinstance(message, Heartbeat) and message.term == self.current_term:
                self.role = Roles.FOLLOWER
                self.voted_for = message.uuid
                self.update(message)
            if (
                isinstance(message, RequestVoteResponse)
                and message.term == self.current_term
                and message.voted_for == self.id
            ):
                self.votes_got += 1
            if self.heartbeat_timer_elapsed():
                if self.votes_got / len(self.seen_hosts) >= 0.5:
                    self.role = Roles.LEADER
                else:
                    self.role = Roles.FOLLOWER

        if self.role == Roles.LEADER:
            if self.heartbeat_timer_elapsed():
                self.reset_heartbeat_timer()
                self.patch_server.message_send(Heartbeat(self.id, self.current_term))
