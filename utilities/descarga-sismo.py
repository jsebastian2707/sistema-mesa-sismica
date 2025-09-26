from obspy import UTCDateTime
from obspy.clients.fdsn import Client
import matplotlib.pyplot as plt

client = Client("IRIS")
t0 = UTCDateTime("2021-07-29T06:15:49")      # Chignik M8.2

# 1) Intenta primero con IU.COL
try:
    st = client.get_waveforms("IU", "COL", "*", "BH?", t0 - 30, t0 + 90)
except Exception:
    print("IU.COL no disponible, probando IU.ANMO…")
    st = client.get_waveforms("IU", "ANMO", "*", "BH?", t0 - 30, t0 + 90)

inv = client.get_stations(network=st[0].stats.network,
                          station=st[0].stats.station,
                          channel=st[0].stats.channel[:2] + "?",
                          starttime=t0-30, endtime=t0+90,
                          level="response")

st.remove_response(inventory=inv, output="ACC")
tr = st[0]

plt.plot(tr.times(), tr.data*1e3)
plt.title(f"{tr.stats.network}.{tr.stats.station}  M8.2 Alaska 2021-07-29")
plt.xlabel("Tiempo (s)")
plt.ylabel("Aceleración (mm/s²)")
plt.grid(); plt.tight_layout(); plt.show()