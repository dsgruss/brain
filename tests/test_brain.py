import asyncio

from brain import __version__, Module, PatchState


def test_version():
    assert __version__ == '0.1.0'

async def test_load():
    mod = Module("test0")
    transport = await mod.start()
    assert mod.get_patch_state() == PatchState.IDLE
    transport.close()

async def test_multiload():
    mod0 = Module("test0")
    mod1 = Module("test1")
    transport0 = await mod0.start()
    transport1 = await mod1.start()
    assert mod0.get_patch_state() == PatchState.IDLE
    assert mod1.get_patch_state() == PatchState.IDLE
    transport0.close()
    transport1.close()

async def test_add_input_jack():
    mod = Module("test0")
    jack = mod.add_input("input0")
    transport = await mod.start()
    assert jack.name == "input0"
    assert mod.get_patch_state() == PatchState.IDLE
    mod.set_patch_enabled(jack, True)
    assert mod.get_patch_state() == PatchState.PATCH_ENABLED
    transport.close()

async def test_add_input_jack_multiload():
    mod0 = Module("test0")
    mod1 = Module("test1")
    jack0 = mod0.add_input("input0")
    jack1 = mod1.add_input("input1")
    transport0 = await mod0.start()
    transport1 = await mod1.start()
    assert mod0.get_patch_state() == PatchState.IDLE
    assert mod1.get_patch_state() == PatchState.IDLE
    mod0.set_patch_enabled(jack0, True)
    assert mod0.get_patch_state() == PatchState.PATCH_ENABLED
    for _ in range(10):
        if mod1.get_patch_state() == PatchState.PATCH_ENABLED:
            break
        await asyncio.sleep(0)
    assert mod1.get_patch_state() == PatchState.PATCH_ENABLED
    mod1.set_patch_enabled(jack1, True)
    assert mod1.get_patch_state() == PatchState.BLOCKED
    transport0.close()
    transport1.close()