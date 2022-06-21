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


def process_update(bs, ls):
    """Helper function to simulate passage of time"""
    start = time.time()
    while time.time() - start < (0.4):
        for b, l in zip(bs, ls):
            while (msg := b.get_message()) is not None:
                l.update(msg)
            l.update(None)


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
    process_update([b0], [l])
    assert l.role == Roles.LEADER


def test_multi_node_leader():
    l0 = LeaderElection("test0", b0 := LocalMessageBroadcast("b0"))
    l1 = LeaderElection("test1", b1 := LocalMessageBroadcast("b1"))
    l2 = LeaderElection("test2", b2 := LocalMessageBroadcast("b2"))
    process_update([b0, b1, b2], [l0, l1, l2])
    roles = [l0.role, l1.role, l2.role]
    assert roles.count(Roles.LEADER) == 1
    assert roles.count(Roles.FOLLOWER) == 2


def test_membership_change():
    l0 = LeaderElection("test0", b0 := LocalMessageBroadcast("b0"))
    process_update([b0], [l0])
    assert l0.role == Roles.LEADER

    l1 = LeaderElection("test1", b1 := LocalMessageBroadcast("b1"))
    l2 = LeaderElection("test2", b2 := LocalMessageBroadcast("b2"))
    process_update([b0, b1, b2], [l0, l1, l2])
    roles = [l0.role, l1.role, l2.role]
    assert roles.count(Roles.LEADER) == 1
    assert roles.count(Roles.FOLLOWER) == 2


def test_reelection():
    l0 = LeaderElection("test0", b0 := LocalMessageBroadcast("b0"))
    process_update([b0], [l0])
    assert l0.role == Roles.LEADER

    l1 = LeaderElection("test1", b1 := LocalMessageBroadcast("b1"))
    l2 = LeaderElection("test2", b2 := LocalMessageBroadcast("b2"))
    process_update([b0, b1, b2], [l0, l1, l2])
    roles = [l0.role, l1.role, l2.role]
    assert roles.count(Roles.LEADER) == 1
    assert roles.count(Roles.FOLLOWER) == 2

    process_update([b1, b2], [l1, l2])
    roles = [l1.role, l2.role]
    assert roles.count(Roles.LEADER) == 1
    assert roles.count(Roles.FOLLOWER) == 1
