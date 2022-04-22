#%%
import imp
import numpy as np
from pyrf.devices.thinkrf import WSA
from pyrf.sweep_device import SweepPlanner
from pyrf.sweep_device_dpmod import SweepDevice, SweepPlanner

from time import time
import matplotlib.pyplot as plt
from pyrf.vrt import vrt_packet_reader
from pyrf.util import (collect_data_and_context, compute_usable_bins, adjust_usable_fstart_fstop,
    trim_to_usable_fstart_fstop, find_saturation)

#%%
RFE_MODE = 'SH'
frange = 100e3
START_FREQ = 5.70e9 - frange
STOP_FREQ = 5.70e9 + frange 
# CENTER_FREQ = 6e9 
SPP = 32 * 512
PPB = 32
RBW = 125e6 / (SPP * PPB)  # 125 MHz is the sampling rate
ATTENUATION = 0
GAIN = 'HIGH'
AVERAGE = 10
DECIMATION = 1 # no decimation

span = STOP_FREQ-START_FREQ

dut = WSA()
addr = '169.254.16.253'
dut.connect(addr)

# dut.reset()
#%%
dut.request_read_perm()
dut.psfm_gain(GAIN)
dut.spp(SPP)
dut.ppb(PPB)
dut.pll_reference('EXT')

#%%
sweepdev = SweepDevice(dut) ## numeric values start being gibberish after this point, but the spectrum capture works fine

#%%
# sweepdev.real_device.flush_captures()
startT = time()
fstart, fstop, spectra_data = sweepdev.capture_power_spectrum(START_FREQ,
                                STOP_FREQ,
                                RBW,
                                {'attenuator':ATTENUATION},
                                mode = RFE_MODE,
                                average = AVERAGE)
freq_range = np.linspace(fstart , fstop, len(spectra_data))
stopT = time()
print(f"Averages = {AVERAGE}, time = {stopT-startT:2.2f} sec, len = {len(spectra_data)}")
plt.plot(freq_range,spectra_data, label = 'Sweep capture')

# %%
dut.scpiset(':sweep:list:stop')
dut.abort()
dut.flush()
dut.flush_captures()
dut.connect(addr)
#%%
dut.attenuator()
# %%
from pyrf.util import collect_data_and_context
collect_data_and_context(dut)
# %%
dut.reset()
# %%
dut.flush_captures()
# %%
dut.scpiget(':syst:capt:mode?')
# %%
dut.scpiset(':SYSTEM:ABORT')
# %%
data  = dut.read()
# %%
print(data)
# %%