from src.gnuradio_adapter import GNUradioAdapter


def test_high_snr_selects_16qam():
    adapter = GNUradioAdapter()
    result = adapter.process([23.0, 11.0, 3.0])

    assert result.channel == 0
    assert result.modulation == "16-QAM"
    assert result.modulation_index == 2
    assert result.enabled is True


def test_better_channel_is_selected():
    adapter = GNUradioAdapter()
    result = adapter.process([3.0, 18.0, 8.0])

    assert result.channel == 1
    assert result.action == "switch_channel"


def test_all_channels_below_threshold():
    adapter = GNUradioAdapter()
    result = adapter.process([-3.0, -2.0, -4.0])

    assert result.enabled is False


def test_recovery_after_bad_channel():
    adapter = GNUradioAdapter()

    adapter.process([-3.0, -2.0, -4.0])
    result = adapter.process([23.0, 11.0, 3.0])

    assert result.channel == 0
    assert result.enabled is True
    assert result.modulation == "16-QAM"
