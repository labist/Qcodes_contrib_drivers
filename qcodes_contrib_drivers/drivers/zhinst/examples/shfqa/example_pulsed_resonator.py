""" Run a triggered frequency sweep with the SHFQA
"""

# Copyright 2021 Zurich Instruments AG

import zhinst.utils
from zhinst.utils.shf_sweeper import (
    ShfSweeper,
    AvgConfig,
    RfConfig,
    SweepConfig,
    TriggerConfig,
)
from zhinst.examples.shfqa.helper_resonator import set_trigger_loopback


def run_example(device_id, do_plot=False):
    """Run a frequency sweep with a SHFQA using an external trigger (trigger in 1 A)

    Requirements:

      - Connect channel 0 input with channel 0 output

    Arguments:

      device_id (str): The ID of the device to run the example with. For
        example, `dev12004` or `shf-dev12004`.

    Returns:

      result (dict): Measurement result.

    """

    # connect device
    apilevel_example = 6
    required_devtype = "SHFQA"
    (daq, dev, _) = zhinst.utils.create_api_session(
        device_id, apilevel_example, required_devtype=required_devtype
    )

    # use the marker output via loopback to trigger the measurment
    # remove this code when using a real external trigger (e.g. an HDAWG)
    set_trigger_loopback(daq, dev)

    # instantiate ShfSweeper
    sweeper = ShfSweeper(daq, dev)

    # configure sweeper
    sweep_config = SweepConfig(
        start_freq=-200e6,
        stop_freq=300e6,
        num_points=51,
        mapping="linear",
        oscillator_gain=0.8,
    )
    avg_config = AvgConfig(dwell_time=100e-6, num_samples=2, mode="pointwise")
    rf_config = RfConfig(channel=0, input_range=0, output_range=0, center_freq=4e9)
    trig_config = TriggerConfig(source="channel0_trigger_input0", level=0)
    sweeper.configure(sweep_config, avg_config, rf_config, trig_config)

    # set to device, can also be ignored
    sweeper.set_to_device()

    # start a sweep
    result = sweeper.run()
    print("Keys in the ShfSweeper result dictionary: ")
    print(result.keys())

    # alternatively, get result after sweep
    result = sweeper.get_result()
    num_points_result = len(result["vector"])
    print(f"Measured at {num_points_result} frequency points.")

    # simple plot over frequency
    if do_plot:
        sweeper.plot()

    return result
