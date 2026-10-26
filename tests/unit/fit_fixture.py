"""FIT totalmente sintético (~3 records/2 laps); cero datos personales."""

from __future__ import annotations

import io
import struct
import zipfile

from fitdecode.utils import compute_crc


def synthetic_fit(
    *, corrupt: bool = False, five_minutes: bool = False, with_pause: bool = False
) -> bytes:
    # FIT spec: mensaje de definición (0x40) seguido de data (0x00).
    def definition(global_num, fields):
        return (
            bytes((0x40, 0, 0))
            + struct.pack("<H", global_num)
            + bytes((len(fields),))
            + b"".join(bytes((number, size, base)) for number, size, base in fields)
        )

    def data(fmt, *values):
        return bytes((0,)) + struct.pack("<" + fmt, *values)

    record_fields = [(253, 4, 0x86), (0, 4, 0x85), (1, 4, 0x85), (6, 2, 0x84), (3, 1, 0x02)]
    lap_fields = [
        (2, 4, 0x86),
        (253, 4, 0x86),
        (9, 4, 0x86),
        (8, 4, 0x86),
        (71, 2, 0x84),
        (23, 1, 0),
        (24, 1, 0),
    ]
    epoch = 1_000_000_000  # FIT epoch seconds (fecha ficticia).
    body = definition(20, record_fields)
    if five_minutes:
        for second in range(300):
            speed = 3000 if second < 150 else 1800  # trabajo y recuperación
            body += data(
                "IiiHB",
                epoch + second,
                100_000_000 + second,
                -200_000_000 - second,
                speed,
                150 if second < 150 else 125,
            )
    else:
        body += data("IiiHB", epoch, 100_000_000, -200_000_000, 3000, 130)
        if with_pause:
            # Mensaje event.timer = stop al segundo 5; no fabricar registros durante la pausa.
            body += definition(21, [(253, 4, 0x86), (0, 1, 0), (1, 1, 0)])
            body += data("IBB", epoch + 5, 0, 1)
            body += definition(20, record_fields)
        body += data("IiiHB", epoch + 5, 100_000_100, -200_000_100, 2800, 132)
        body += data("IiiHB", epoch + 5, 100_000_100, -200_000_100, 2800, 133)
    body += definition(19, lap_fields)
    split = 150 if five_minutes else 5
    body += data("IIIIHBB", epoch, epoch + split, 50000, split * 1000, 0, 0, 0)
    body += data("IIIIHBB", epoch + split, epoch + 2 * split, 50000, split * 1000, 1, 1, 0)
    header = struct.pack("<BBHI4s", 14, 0x10, 2100, len(body), b".FIT")
    header += struct.pack("<H", compute_crc(header))
    raw = header + body
    raw += struct.pack("<H", compute_crc(raw))
    return raw[:-1] + b"\x00" if corrupt else raw


def synthetic_zip(raw: bytes | None = None) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("file/ACTIVITY.fit", synthetic_fit() if raw is None else raw)
    return out.getvalue()
