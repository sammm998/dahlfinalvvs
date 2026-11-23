"""Hängarna tillbaka till modellen: en IFC4-fil där varje SmartHanger är ett IfcDiscreteAccessory med ID, läge,
revision, status, artiklar, kaplängd, last och GlobalId på de rör den bär (Pset_SmartHanger), och en enkel kropp
(takjärnet som en balk, pendlarna som stänger) så att den syns i samordningsmodellen bredvid rören."""
from __future__ import annotations

import time
import uuid
from typing import Any

_B64 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"


def guid(seed: str) -> str:
    """IFC:s komprimerade GlobalId (22 tecken), stabilt för samma hängare och projekt."""
    n = uuid.uuid5(uuid.NAMESPACE_URL, "smarthanger:" + seed).int
    out = [_B64[(n >> (6 * i)) & 63] for i in range(22)]
    out[-1] = _B64[(n >> 126) & 3]
    return "".join(reversed(out))


def _s(text: Any) -> str:
    t = str(text if text is not None else "")
    out = []
    for ch in t.replace("'", "''"):
        out.append(ch if ord(ch) < 128 else "\\X2\\%04X\\X0\\" % ord(ch))
    return "'" + "".join(out) + "'"


def export(hangers: list[dict[str, Any]], project: str, revision: str = "A") -> str:
    L: list[str] = []
    n = [0]

    def add(s: str) -> int:
        n[0] += 1
        L.append(f"#{n[0]}={s};")
        return n[0]

    pt = lambda x, y, z: add(f"IFCCARTESIANPOINT(({float(x):.1f},{float(y):.1f},{float(z):.1f}))")
    d = lambda x, y, z: add(f"IFCDIRECTION(({float(x)},{float(y)},{float(z)}))")
    origin = pt(0, 0, 0)
    zax, xax = d(0, 0, 1), d(1, 0, 0)
    world = add(f"IFCAXIS2PLACEMENT3D(#{origin},#{zax},#{xax})")
    ctx = add(f"IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-05,#{world},$)")
    body = add(f"IFCGEOMETRICREPRESENTATIONSUBCONTEXT('Body','Model',*,*,*,*,#{ctx},$,.MODEL_VIEW.,$)")
    mm = add("IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.)")
    units = add(f"IFCUNITASSIGNMENT((#{mm}))")
    proj = add(f"IFCPROJECT({_s(guid(project + ':project'))},$,{_s(project or 'Projekt')},{_s('SmartHangers revision ' + revision)},$,$,$,(#{ctx}),#{units})")
    site_pl = add(f"IFCLOCALPLACEMENT($,#{world})")
    building = add(f"IFCBUILDING({_s(guid(project + ':building'))},$,'Byggnad',$,$,#{site_pl},$,$,.ELEMENT.,$,$,$)")
    add(f"IFCRELAGGREGATES({_s(guid(project + ':agg'))},$,$,$,#{proj},(#{building}))")
    storeys: dict[str, int] = {}
    contained: dict[str, list[int]] = {}
    for h in hangers:
        st = h.get("storey") or "?"
        if st not in storeys:
            storeys[st] = add(f"IFCBUILDINGSTOREY({_s(guid(project + ':storey:' + st))},$,{_s(st)},$,$,#{site_pl},$,$,.ELEMENT.,$)")
            contained[st] = []
        p = h["position"]
        x, y = p["x"], p["y"]
        tj = h.get("takjarn") or {}
        rods = h.get("rods") or []
        rod_len = rods[0].get("length_mm") if rods else None
        z_top = p["z"] if p.get("z") is not None else (max(pp["centre_z"] for pp in h["pipes"]) + 200)
        rl = float(rod_len or 300)
        loc = add(f"IFCAXIS2PLACEMENT3D(#{pt(x, y, z_top - rl)},#{zax},#{xax})")
        place = add(f"IFCLOCALPLACEMENT(#{site_pl},#{loc})")
        items = []
        if tj:
            length = tj["length_mm"]
            # takjärnet: en låda 41x41 längs stråkets tvärriktning (förenklad: x-axeln i hängarens plan)
            prof = add(f"IFCRECTANGLEPROFILEDEF(.AREA.,$,$,41.,41.)")
            pos = add(f"IFCAXIS2PLACEMENT3D(#{pt(-length / 2, 0, -20.5)},#{d(1, 0, 0)},#{d(0, 0, 1)})")
            items.append(add(f"IFCEXTRUDEDAREASOLID(#{prof},#{pos},#{zax},{float(length)})"))
            offs = [r.get("at_mm", 0) - length / 2 for r in rods]
        else:
            offs = [0.0]
        for o in offs:
            c = add("IFCCIRCLEPROFILEDEF(.AREA.,$,$,5.)")
            pos = add(f"IFCAXIS2PLACEMENT3D(#{pt(o, 0, 0)},#{zax},#{xax})")
            items.append(add(f"IFCEXTRUDEDAREASOLID(#{c},#{pos},#{zax},{rl})"))
        shape = add(f"IFCSHAPEREPRESENTATION(#{body},'Body','SweptSolid',({','.join('#%d' % i for i in items)}))")
        pds = add(f"IFCPRODUCTDEFINITIONSHAPE($,$,(#{shape}))")
        el = add(f"IFCDISCRETEACCESSORY({_s(guid(project + ':' + h['id']))},$,{_s(h['id'])},{_s('SmartHanger ' + h['kind'])},'SmartHanger',#{place},#{pds},{_s(h['id'])},.USERDEFINED.)")
        contained[st].append(el)
        props = [("ID", h["id"]), ("Projekt", project), ("Revision", h.get("revision") or revision), ("Status", h.get("status")),
                 ("Typ", h["kind"]), ("Vaning", st), ("Zon", h.get("zone")), ("Pendellangd_mm", rod_len),
                 ("Takjarnslangd_mm", tj.get("length_mm")), ("Hojdkalla", h.get("height_source")),
                 ("Kolli", (h.get("pack") or {}).get("kolli")), ("Ror", ", ".join(str(pp.get("dn") or pp.get("od")) for pp in h["pipes"])),
                 ("Ror_GlobalId", ", ".join(str(pp.get("id")) for pp in h["pipes"])),
                 ("Gangstang", rods[0].get("size") if rods else None),
                 ("Beraknad_langd_mm", rods[0].get("calc_mm") if rods else None),
                 ("Last_kN", h.get("load_kn")), ("Punktlast_kg", h.get("point_load_kg")),
                 ("Infastning", h.get("anchor")), ("Bjalklagstyp", (h.get("slab") or {}).get("type")),
                 ("Avstand_vagg_mm", (h.get("wall") or {}).get("mm")),
                 ("Avstand_undertak_mm", (h.get("ceiling_clearance") or {}).get("mm")),
                 ("Artiklar", "; ".join(f"{b['qty']} x {b['text']}" + (f" {b['length_mm']}" if b.get("length_mm") else "")
                                        for b in h.get("bom") or [])[:2000]),
                 ("Flaggor", "; ".join(h.get("flags") or [])[:2000] or None)]
        pids = []
        for k, v in props:
            if v is None:
                continue
            if isinstance(v, bool):
                v = "ja" if v else "nej"
            val = (f"IFCINTEGER({int(v)})" if isinstance(v, int) else f"IFCREAL({float(v):.4f})" if isinstance(v, float)
                   else f"IFCTEXT({_s(v)})" if len(str(v)) > 255 else f"IFCLABEL({_s(v)})")
            pids.append(add(f"IFCPROPERTYSINGLEVALUE({_s(k)},$,{val},$)"))
        ps = add(f"IFCPROPERTYSET({_s(guid(project + ':ps:' + h['id']))},$,'Pset_SmartHanger',$,({','.join('#%d' % i for i in pids)}))")
        add(f"IFCRELDEFINESBYPROPERTIES({_s(guid(project + ':rdp:' + h['id']))},$,$,$,(#{el}),#{ps})")
    if storeys:
        add(f"IFCRELAGGREGATES({_s(guid(project + ':aggst'))},$,$,$,#{building},({','.join('#%d' % i for i in storeys.values())}))")
    for st, els in contained.items():
        if els:
            add(f"IFCRELCONTAINEDINSPATIALSTRUCTURE({_s(guid(project + ':cont:' + st))},$,$,$,({','.join('#%d' % i for i in els)}),#{storeys[st]})")
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    head = ["ISO-10303-21;", "HEADER;", "FILE_DESCRIPTION(('ViewDefinition [ReferenceView]'),'2;1');",
            f"FILE_NAME({_s('smarthangers.ifc')},{_s(stamp)},(''),(''),'Dahl SmartHangers','Dahl SmartHangers','');",
            "FILE_SCHEMA(('IFC4'));", "ENDSEC;", "DATA;"]
    return "\n".join(head + L + ["ENDSEC;", "END-ISO-10303-21;", ""])
