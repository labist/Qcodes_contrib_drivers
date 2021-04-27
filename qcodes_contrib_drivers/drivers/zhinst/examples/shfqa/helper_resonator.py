""" Run a triggered frequency sweep with the SHFQA
"""

# Copyright 2021 Zurich Instruments AG

import time


def set_trigger_loopback(daq, dev):
    """
    Start a continuous trigger pulse from marker 1 A using the internal loopback to trigger in 1 A
    """

    m_ch = 0
    continuous_trig = 1
    daq.setInt(f"/{dev}/RAW/MARKERS/{m_ch}/TESTSOURCE", continuous_trig)
    daq.setDouble(f"/{dev}/RAW/MARKERS/{m_ch}/FREQUENCY", 1e3)
    daq.setInt(f"/{dev}/RAW/TRIGGERS/{m_ch}/LOOPBACK", 1)
    time.sleep(0.2)
