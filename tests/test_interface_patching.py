from brain import __version__, Module, PatchState


def test_version():
    assert __version__ == "0.1.0"


def test_load():
    mod = Module("test0")
    assert mod.get_patch_state() == PatchState.IDLE


def test_multiload():
    mod0 = Module("test0")
    mod1 = Module("test1")
    assert mod0.get_patch_state() == PatchState.IDLE
    assert mod1.get_patch_state() == PatchState.IDLE


def test_add_input_jack():
    mod = Module("test0")
    jack = mod.add_input("input0")
    assert jack.name == "input0"
    assert mod.get_patch_state() == PatchState.IDLE
    mod.set_patch_enabled(jack, True)
    assert mod.get_patch_state() == PatchState.PATCH_ENABLED


def test_add_input_jack_multiload():
    mod0 = Module("test0")
    mod1 = Module("test1")
    jack0 = mod0.add_input("input0")
    jack1 = mod1.add_input("input1")
    assert mod0.get_patch_state() == PatchState.IDLE
    assert mod1.get_patch_state() == PatchState.IDLE
    mod0.set_patch_enabled(jack0, True)
    assert mod0.get_patch_state() == PatchState.PATCH_ENABLED
    for _ in range(10):
        mod0.update()
        mod1.update()
        if mod1.get_patch_state() == PatchState.PATCH_ENABLED:
            break
    assert mod1.get_patch_state() == PatchState.PATCH_ENABLED
    mod1.set_patch_enabled(jack1, True)
    assert mod1.get_patch_state() == PatchState.BLOCKED
