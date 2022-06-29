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
from typing import Dict, Final, Optional, Set

from brain.protocol import (
    GlobalStateUpdate,
    LocalState,
    Directive,
    Heartbeat,
    HeartbeatResponse,
    PatchState,
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
        self.seen_hosts: Dict[str, Optional[LocalState]] = {}
        self.local_state = LocalState(held_inputs=[], held_outputs=[])
        self.last_update = None
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

    def update(self, message: Optional[Directive]):

        self.seen_hosts[self.id] = self.local_state

        if message is not None:
            if message.uuid not in self.seen_hosts:
                self.seen_hosts[message.uuid] = None
            if message.uuid == self.id:
                return

        if isinstance(message, Heartbeat):
            if message.term < self.current_term:
                self.patch_server.message_send(
                    HeartbeatResponse(
                        uuid=self.id, term=self.current_term, success=False
                    )
                )
            else:
                if message.term > self.current_term:
                    self.current_term = message.term
                    self.role = Roles.FOLLOWER
                    self.voted_for = message.uuid
                self.reset_election_timer()
                self.patch_server.message_send(
                    HeartbeatResponse(
                        uuid=self.id,
                        term=self.current_term,
                        success=True,
                        iteration=message.iteration,
                        state=self.local_state,
                    )
                )

        if isinstance(message, RequestVote):
            if message.term < self.current_term:
                self.patch_server.message_send(
                    RequestVoteResponse(
                        uuid=self.id,
                        term=self.current_term,
                        voted_for=message.uuid,
                        vote_granted=False,
                    )
                )

            else:
                if message.term > self.current_term:
                    self.current_term = message.term
                    self.role = Roles.FOLLOWER
                    self.voted_for = message.uuid
                if self.voted_for is None or self.voted_for == message.uuid:
                    self.reset_election_timer()
                    self.patch_server.message_send(
                        RequestVoteResponse(
                            uuid=self.id,
                            term=self.current_term,
                            voted_for=message.uuid,
                            vote_granted=True,
                        )
                    )

        if self.role == Roles.FOLLOWER and self.election_timer_elapsed():
            self.role = Roles.CANDIDATE
            self.current_term += 1
            self.voted_for = self.id
            self.seen_hosts = {self.id: self.local_state}
            self.votes_got = 1
            self.reset_election_timer()
            self.reset_heartbeat_timer()
            self.patch_server.message_send(
                RequestVote(uuid=self.id, term=self.current_term)
            )

        if self.role == Roles.CANDIDATE:
            if (
                message
                and isinstance(message, Heartbeat)
                and message.term == self.current_term
            ):
                self.role = Roles.FOLLOWER
                self.voted_for = message.uuid
                self.update(message)
            if (
                message
                and isinstance(message, RequestVoteResponse)
                and message.term == self.current_term
                and message.voted_for == self.id
            ):
                if message.vote_granted:
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
                # Currently, this sends an update every heartbeat, meaning it could be up to 100 ms
                # before a change in the patch status is registered. Future mitigations would be to
                # use a third timer for the heartbeat response and/or send the state update as soon
                # as all known module have responded.
                self.check_global_state_update()

                self.reset_heartbeat_timer()
                self.iteration += 1
                self.patch_server.message_send(
                    Heartbeat(
                        uuid=self.id,
                        term=self.current_term,
                        iteration=self.iteration,
                    )
                )
            if message and isinstance(message, HeartbeatResponse):
                if (
                    message.success
                    and message.iteration == self.iteration
                    and message.state is not None
                ):
                    # A timeout value should be added here for modules that go offline
                    self.seen_hosts[message.uuid] = message.state

    def check_global_state_update(self):
        inputs = []
        outputs = []
        for v in self.seen_hosts.values():
            if v is not None:
                inputs.extend(v.held_inputs)
                outputs.extend(v.held_outputs)
        if len(inputs) == 0 and len(outputs) == 0:
            update = GlobalStateUpdate(self.id, PatchState.IDLE, None, None)
        elif len(inputs) == 1 and len(outputs) == 0:
            update = GlobalStateUpdate(
                self.id, PatchState.PATCH_ENABLED, inputs[0], None
            )
        elif len(inputs) == 0 and len(outputs) == 1:
            update = GlobalStateUpdate(
                self.id, PatchState.PATCH_ENABLED, None, outputs[0]
            )
        elif len(inputs) == 1 and len(outputs) == 1:
            update = GlobalStateUpdate(
                self.id, PatchState.PATCH_TOGGLED, inputs[0], outputs[0]
            )
        else:
            update = GlobalStateUpdate(self.id, PatchState.BLOCKED, None, None)
        if update != self.last_update:
            self.last_update = update
            self.patch_server.message_send(update)

    def update_local_state(self, local_state):
        self.local_state = local_state
