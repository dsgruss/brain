from brain.parsers import MessageParser
from brain.protocol import (
    Halt,
    Update,
    LocalState,
    HeldInputJack,
    SnapshotRequest,
    SnapshotResponse,
    PatchConnection,
    Directive,
)


def test_halt():
    m = MessageParser()
    msg = Halt(uuid="GLOBAL")
    assert msg == m.parse_directive(m.create_directive(msg))


def test_update():
    m = MessageParser()
    msg = Update(
            uuid="testuuid",
            local_state=LocalState(
                held_inputs=[HeldInputJack(uuid="testuuid", id="1")], held_outputs=[]
            ),
        )
    print(m.create_directive(msg))
    assert str(msg) == str(m.parse_directive(m.create_directive(msg)))


def test_snapshotrequest():
    m = MessageParser()
    msg = SnapshotRequest(uuid="testuuid")
    assert str(msg) == str(m.parse_directive(m.create_directive(msg)))


def test_snapshotresponse():
    m = MessageParser()
    msg = SnapshotResponse(
            uuid="testuuid", data="123912378123", patched=[]
        )
    assert str(msg) == str(m.parse_directive(m.create_directive(msg)))


def test_snapshotresponse():
    m = MessageParser()
    msg = SnapshotResponse(
            uuid="testuuid",
            data="123912378123",
            patched=[
                PatchConnection(
                    input_uuid="testuuid",
                    input_jack_id="2",
                    output_uuid="testuuid2",
                    output_jack_id="1",
                )
            ],
        )
    assert str(msg) == str(m.parse_directive(m.create_directive(msg)))
