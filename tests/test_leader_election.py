from base64 import b16encode
import logging
import time
from brain.leader_election import LeaderElection, Roles


class LocalMessageBroadcast:
    """Test class used to simply wire message broadcasts together"""

    messages = []

    def __init__(self, id) -> None:
        self.message_idx = len(self.messages)
        self.id = id
        print(self.id + " Interface Created")

    def message_send(self, message):
        print(self.id + " => " + str(message))
        self.messages.append(message)

    def get_message(self):
        if self.message_idx == len(self.messages):
            return None
        else:
            self.message_idx += 1
            print(self.id + " <= " + str(self.messages[self.message_idx - 1]))
            return self.messages[self.message_idx - 1]


def test_localbroadcast():
    b0 = LocalMessageBroadcast("b0")
    b1 = LocalMessageBroadcast("b1")
    assert b0.get_message() is None
    assert b1.get_message() is None
    b0.message_send("TESTTESTTEST")
    assert b0.get_message() == "TESTTESTTEST"
    assert b0.get_message() is None
    assert b1.get_message() == "TESTTESTTEST"
    assert b1.get_message() is None

def test_instantiation():
    l = LeaderElection("test0", LocalMessageBroadcast("b"))
    assert l.role == Roles.FOLLOWER

def test_lone_node_leader():
    b0 = LocalMessageBroadcast("b0")
    l = LeaderElection("test0", b0)
    start = time.time()
    while time.time() - start < (l.election_timeout_interval[1] / 1000):
        while (msg := b0.get_message()) is not None:
            l.update(msg)
        l.update(None)
    assert l.role == Roles.LEADER

def test_multi_node_leader():
    l0 = LeaderElection("test0", b0 := LocalMessageBroadcast("b0"))
    l1 = LeaderElection("test1", b1 := LocalMessageBroadcast("b1"))
    l2 = LeaderElection("test2", b2 := LocalMessageBroadcast("b2"))
    start = time.time()
    while time.time() - start < (l0.election_timeout_interval[1] / 1000):
        while (msg := b0.get_message()) is not None:
            l0.update(msg)
        while (msg := b1.get_message()) is not None:
            l1.update(msg)
        while (msg := b2.get_message()) is not None:
            l2.update(msg)
        l0.update(None)
        l1.update(None)
        l2.update(None)
    roles = [l0.role, l1.role, l2.role]
    assert roles.count(Roles.LEADER) == 1
    assert roles.count(Roles.FOLLOWER) == 2

def test_membership_change():
    l0 = LeaderElection("test0", b0 := LocalMessageBroadcast("b0"))
    start = time.time()
    while time.time() - start < (l0.election_timeout_interval[1] / 1000):
        while (msg := b0.get_message()) is not None:
            l0.update(msg)
        l0.update(None)
    assert l0.role == Roles.LEADER

    l1 = LeaderElection("test1", b1 := LocalMessageBroadcast("b1"))
    l2 = LeaderElection("test2", b2 := LocalMessageBroadcast("b2"))
    start = time.time()
    while time.time() - start < (l0.election_timeout_interval[1] / 1000):
        while (msg := b0.get_message()) is not None:
            l0.update(msg)
        while (msg := b1.get_message()) is not None:
            l1.update(msg)
        while (msg := b2.get_message()) is not None:
            l2.update(msg)
        l0.update(None)
        l1.update(None)
        l2.update(None)
    roles = [l0.role, l1.role, l2.role]
    assert roles.count(Roles.LEADER) == 1
    assert roles.count(Roles.FOLLOWER) == 2

def test_reelection():
    l0 = LeaderElection("test0", b0 := LocalMessageBroadcast("b0"))
    start = time.time()
    while time.time() - start < (l0.election_timeout_interval[1] / 1000):
        while (msg := b0.get_message()) is not None:
            l0.update(msg)
        l0.update(None)
    assert l0.role == Roles.LEADER

    l1 = LeaderElection("test1", b1 := LocalMessageBroadcast("b1"))
    l2 = LeaderElection("test2", b2 := LocalMessageBroadcast("b2"))
    start = time.time()
    while time.time() - start < (l0.election_timeout_interval[1] / 1000):
        while (msg := b0.get_message()) is not None:
            l0.update(msg)
        while (msg := b1.get_message()) is not None:
            l1.update(msg)
        while (msg := b2.get_message()) is not None:
            l2.update(msg)
        l0.update(None)
        l1.update(None)
        l2.update(None)
    roles = [l0.role, l1.role, l2.role]
    assert roles.count(Roles.LEADER) == 1
    assert roles.count(Roles.FOLLOWER) == 2

    start = time.time()
    while time.time() - start < (l0.election_timeout_interval[1] / 1000):
        while (msg := b1.get_message()) is not None:
            l1.update(msg)
        while (msg := b2.get_message()) is not None:
            l2.update(msg)
        l1.update(None)
        l2.update(None)
    roles = [l1.role, l2.role]
    assert roles.count(Roles.LEADER) == 1
    assert roles.count(Roles.FOLLOWER) == 1