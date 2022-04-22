#%%
from math import ceil
import numpy as np
from pyrf.devices.thinkrf import WSA
from pyrf.sweep_device import SweepDevice, SweepSettings
from pyrf.util import capture_spectrum, collect_data_and_context

from time import time
import matplotlib.pyplot as plt
from pyrf.vrt import vrt_packet_reader
import time
#%%
RFE_MODE = 'ZIF'
CENTER_FREQ = 5.7000e9  + 0.000e6
SPP = int(2**8)
PPB = 1
ATTENUATION = 0
GAIN = 'HIGH'
DECIMATION = 0 # no decimation

dut = WSA()
dut.connect('169.254.16.253')

dut.reset()
dut.request_read_perm()
dut.flush()

dut.pll_reference('EXT')
dut.rfe_mode(RFE_MODE)
dut.freq(CENTER_FREQ)
dut.decimation(DECIMATION)

dut.spp(SPP)
dut.ppb(PPB)


dut.flush()
time.sleep(0.25)
dut.capture( SPP, PPB )

for i in range(PPB):
    data, context = collect_data_and_context(dut)
    print(data.data.__len__())


i = np.array([ z[0] for z in data.data.numpy_array() ], dtype=float)
q = np.array([ z[1] for z in data.data.numpy_array() ], dtype=float)
t = np.arange(0, len(i), 1) / 125e0

fig, axes = plt.subplots(2,1,sharex=True)
axes[0].plot(t, 20*np.log10( (i*i + q*q ) /2**13/len(i) ) )
axes[1].plot(t, np.arctan2(q,i))
plt.xlabel('time (us)')

# %%
