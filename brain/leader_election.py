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

from enum import Enum
from random import randrange
from time import perf_counter_ns
from typing import Final, Set

from brain.proto.patching_pb2 import (
    LocalState,
    Directive,
    Heartbeat,
    HeartbeatResponse,
    RequestVote,
    RequestVoteResponse,
)


class Roles(Enum):
    FOLLOWER = "FOLLOWER"
    CANDIDATE = "CANDIDATE"
    LEADER = "LEADER"


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
        self.local_state = LocalState(held_inputs=[], held_outputs=[])
        self.reset_election_timer()

    def time_ms(self):
        return perf_counter_ns() // 1000000

    def reset_election_timer(self):
        self.election_time = self.time_ms()
        self.election_timeout = randrange(*self.election_timeout_interval)

    def reset_heartbeat_timer(self):
        self.heartbeat_time = self.time_ms()

    def election_timer_elapsed(self):
        return (self.time_ms() - self.election_time) > self.election_timeout

    def heartbeat_timer_elapsed(self):
        return (self.time_ms() - self.heartbeat_time) > self.response_timeout

    def update(self, message: Directive):

        if message is not None:
            for field in [
                "heartbeat",
                "heartbeat_response",
                "global_state_update",
                "request_vote",
                "request_vote_response",
            ]:
                try:
                    id = getattr(message, field).uuid
                    self.seen_hosts.add(id)
                    if id == self.id:
                        return
                except AttributeError:
                    continue

        if message and message.HasField("heartbeat"):
            if message.heartbeat.term < self.current_term:
                self.patch_server.message_send(
                    Directive(
                        heartbeat_response=HeartbeatResponse(
                            uuid=self.id, term=self.current_term, success=False
                        )
                    )
                )
            else:
                if message.heartbeat.term > self.current_term:
                    self.current_term = message.heartbeat.term
                    self.role = Roles.FOLLOWER
                    self.voted_for = message.heartbeat.uuid
                self.reset_election_timer()
                self.patch_server.message_send(
                    Directive(
                        heartbeat_response=HeartbeatResponse(
                            uuid=self.id,
                            term=self.current_term,
                            success=True,
                            iteration=message.heartbeat.iteration,
                            state=self.local_state,
                        )
                    )
                )

        if message and message.HasField("request_vote"):
            if message.request_vote.term < self.current_term:
                self.patch_server.message_send(
                    Directive(
                        request_vote_response=RequestVoteResponse(
                            uuid=self.id,
                            term=self.current_term,
                            voted_for=message.request_vote.uuid,
                            vote_granted=False,
                        )
                    )
                )
            else:
                if message.request_vote.term > self.current_term:
                    self.current_term = message.request_vote.term
                    self.role = Roles.FOLLOWER
                    self.voted_for = None
                if (
                    self.voted_for is None
                    or self.voted_for == message.request_vote.uuid
                ):
                    self.reset_election_timer()
                    self.patch_server.message_send(
                        Directive(
                            request_vote_response=RequestVoteResponse(
                                uuid=self.id,
                                term=self.current_term,
                                voted_for=message.request_vote.uuid,
                                vote_granted=True,
                            )
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
            self.patch_server.message_send(
                Directive(
                    request_vote=RequestVote(uuid=self.id, term=self.current_term)
                )
            )

        if self.role == Roles.CANDIDATE:
            if (
                message
                and message.HasField("heartbeat")
                and message.heartbeat.term == self.current_term
            ):
                self.role = Roles.FOLLOWER
                self.voted_for = message.heartbeat.uuid
                self.update(message)
            if (
                message
                and message.HasField("request_vote_response")
                and message.request_vote_response.term == self.current_term
                and message.request_vote_response.voted_for == self.id
            ):
                if message.request_vote_response.vote_granted:
                    self.votes_got += 1
                else:
                    self.role = Roles.FOLLOWER
            if self.heartbeat_timer_elapsed():
                if self.votes_got / len(self.seen_hosts) >= 0.5:
                    self.role = Roles.LEADER
                    self.iteration = 0
                else:
                    self.role = Roles.FOLLOWER

        if self.role == Roles.LEADER:
            if self.heartbeat_timer_elapsed():
                self.reset_heartbeat_timer()
                self.iteration += 1
                self.patch_server.message_send(
                    Directive(
                        heartbeat=Heartbeat(
                            uuid=self.id,
                            term=self.current_term,
                            iteration=self.iteration,
                        )
                    )
                )
