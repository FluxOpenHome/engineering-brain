"""Equipment property schemas for specification authoring (architecture 6.6).

Python data, not database rows: a template is a parameter list with units (IEC CDD / ECLASS
style), the standards it normally references (clause IDs and names only, never text: P10),
and a cross-discipline interface checklist. `interface` on a parameter names the discipline
that parameter is an interface to (motor rated power -> electrical, dry mass -> structural).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Parameter:
    name: str
    unit: str | None
    description: str
    required: bool = True
    interface: str | None = None  # discipline this parameter is an interface to

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InterfaceItem:
    topic: str
    from_discipline: str
    to_discipline: str
    check: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Template:
    key: str
    name: str
    discipline: str
    description: str
    standards_refs: list[str]
    parameters: list[Parameter]
    interface_checklist: list[InterfaceItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "discipline": self.discipline,
            "description": self.description,
            "standards_refs": list(self.standards_refs),
            "parameters": [p.to_dict() for p in self.parameters],
            "interface_checklist": [i.to_dict() for i in self.interface_checklist],
        }


def P(
    name: str, unit: str | None, description: str, required: bool = True, interface: str | None = None
) -> Parameter:
    return Parameter(name, unit, description, required, interface)


def I(topic: str, frm: str, to: str, check: str) -> InterfaceItem:  # noqa: E743 - short constructor
    return InterfaceItem(topic, frm, to, check)


# Checklist items shared by rotating / powered equipment.
_POWERED = [
    I(
        "Electrical load",
        "mechanical",
        "electrical",
        "Motor rated power, starting current and duty match the switchgear feeder, cable and "
        "transformer sizing.",
    ),
    I(
        "Heat rejection",
        "mechanical",
        "hvac",
        "Heat dissipated to the room (motor and drive losses) is included in the HVAC cooling load.",
    ),
    I(
        "Mass and footprint",
        "mechanical",
        "structural",
        "Dry and operating mass, centre of gravity and anchor bolt pattern are given to the "
        "foundation design.",
    ),
    I(
        "Dynamic loads",
        "mechanical",
        "structural",
        "Unbalance forces, seismic and short-circuit torque loads are given for the foundation or support.",
    ),
    I(
        "I&C signals",
        "mechanical",
        "ic",
        "Instrument list, signal types (4-20 mA, HART, fieldbus), fail-safe states and permissives "
        "are agreed.",
    ),
    I(
        "Noise",
        "mechanical",
        "hse",
        "Sound pressure level at 1 m is below the area limit or acoustic treatment is specified.",
    ),
    I(
        "Maintenance access",
        "mechanical",
        "civil",
        "Lifting points, laydown space, crane hook height and withdrawal clearances fit the building layout.",
    ),
    I(
        "Utilities",
        "mechanical",
        "fluid",
        "Cooling water, seal flush, instrument air and lubrication supplies are listed with pressure, "
        "flow and quality.",
    ),
]

TEMPLATES: dict[str, Template] = {}


def _register(t: Template) -> Template:
    TEMPLATES[t.key] = t
    return t


_register(
    Template(
        key="centrifugal_pump",
        name="Centrifugal pump",
        discipline="fluid",
        description="Horizontal or vertical centrifugal pump with electric motor drive.",
        standards_refs=[
            "ISO 5199",
            "ISO 2858",
            "ISO 9906 (Grade 1B/2B)",
            "API 610 / ISO 13709",
            "ISO 21049",
            "IEC 60034-30-1",
            "ISO 10816-7",
        ],
        parameters=[
            P("Service / fluid", None, "Pumped fluid, temperature and composition."),
            P("Rated flow", "m3/h", "Guaranteed flow at the rated point."),
            P("Differential head", "m", "Total differential head at rated flow."),
            P(
                "Minimum continuous stable flow",
                "m3/h",
                "Lowest flow for continuous operation.",
                required=False,
            ),
            P("NPSH available", "m", "NPSH available at the pump suction, rated flow.", interface="fluid"),
            P("NPSH required margin", "m", "Required NPSHa - NPSHr margin at rated flow.", required=False),
            P("Design pressure", "bar(g)", "Casing design pressure (MAWP)."),
            P("Design temperature", "degC", "Casing design temperature."),
            P("Suction pressure", "bar(g)", "Rated suction pressure."),
            P("Fluid density", "kg/m3", "Density at pumping temperature."),
            P("Fluid viscosity", "cSt", "Viscosity at pumping temperature."),
            P("Casing material", None, "Pressure casing material grade (e.g. ASTM A216 WCB)."),
            P("Impeller material", None, "Impeller material grade."),
            P("Shaft seal type", None, "Mechanical seal arrangement and API 682 plan.", required=False),
            P(
                "Nozzle sizes and rating",
                None,
                "Suction/discharge nozzle size and flange rating.",
                interface="fluid",
            ),
            P("Hydraulic efficiency", "%", "Efficiency at rated point.", required=False),
            P(
                "Motor rated power",
                "kW",
                "Motor nameplate power with service factor.",
                interface="electrical",
            ),
            P("Motor voltage", "V", "Supply voltage.", interface="electrical"),
            P("Frequency", "Hz", "Supply frequency.", interface="electrical"),
            P("Motor speed", "rpm", "Synchronous or rated speed."),
            P(
                "Motor efficiency class",
                None,
                "IEC 60034-30-1 class (IE3/IE4).",
                required=False,
                interface="electrical",
            ),
            P(
                "Starting method",
                None,
                "Direct on line, soft starter or VSD.",
                required=False,
                interface="electrical",
            ),
            P("Sound pressure level", "dB(A)", "At 1 m from the unit.", interface="hse"),
            P("Dry mass", "kg", "Mass of complete unit on baseplate.", interface="structural"),
            P("Operating mass", "kg", "Mass filled with fluid.", interface="structural"),
            P("Vibration limit", "mm/s", "RMS velocity limit per ISO 10816-7.", required=False),
            P("Performance test", None, "Acceptance test grade and witnessing (ISO 9906)."),
            P(
                "Area classification",
                None,
                "Hazardous area zone, gas group, temperature class.",
                required=False,
                interface="electrical",
            ),
            P(
                "Instrumentation",
                None,
                "Bearing temperature, vibration, seal pot level.",
                required=False,
                interface="ic",
            ),
        ],
        interface_checklist=_POWERED,
    )
)

_register(
    Template(
        key="control_valve",
        name="Control valve",
        discipline="fluid",
        description="Throttling control valve with actuator and positioner.",
        standards_refs=[
            "IEC 60534-1",
            "IEC 60534-2-1",
            "IEC 60534-4",
            "IEC 60534-8-3",
            "ANSI/ISA-75.01.01",
            "ASME B16.34",
            "ASME B16.5",
            "IEC 61508 (SIL where applicable)",
        ],
        parameters=[
            P("Service / fluid", None, "Fluid, phase and composition."),
            P("Line size", None, "Nominal pipe size (DN/NPS).", interface="fluid"),
            P("Pressure class", None, "Flange rating (PN/Class).", interface="fluid"),
            P("Design pressure", "bar(g)", "Body design pressure."),
            P("Design temperature", "degC", "Body design temperature."),
            P("Maximum flow", "m3/h", "Flow at maximum case."),
            P("Normal flow", "m3/h", "Flow at normal case."),
            P("Minimum flow", "m3/h", "Flow at minimum case."),
            P("Inlet pressure", "bar(g)", "At maximum/normal/minimum cases."),
            P("Differential pressure", "bar", "Across the valve at each case."),
            P("Required Cv/Kv", "m3/h", "Calculated flow coefficient (Kv) at each case."),
            P("Rangeability", None, "Required turndown ratio.", required=False),
            P("Shut-off class", None, "Leakage class per IEC 60534-4."),
            P("Flow characteristic", None, "Linear / equal percentage / quick opening."),
            P("Body material", None, "Body and bonnet material grade."),
            P("Trim material", None, "Plug, seat and cage materials."),
            P("Noise limit", "dB(A)", "Predicted noise at 1 m per IEC 60534-8-3.", interface="hse"),
            P("Cavitation / flashing", None, "Allowable sigma or anti-cavitation trim need.", required=False),
            P("Actuator type", None, "Pneumatic diaphragm, piston or electric.", interface="ic"),
            P("Fail action", None, "Fail open / fail closed / fail last.", interface="ic"),
            P("Stroking time", "s", "Full-stroke time, open and close.", required=False, interface="ic"),
            P(
                "Instrument air supply",
                "bar(g)",
                "Supply pressure and quality (ISO 8573-1).",
                interface="fluid",
            ),
            P("Positioner signal", None, "4-20 mA / HART / fieldbus; feedback signals.", interface="ic"),
            P(
                "Hazardous area",
                None,
                "Zone, gas group, temperature class for accessories.",
                required=False,
                interface="electrical",
            ),
            P("Mass", "kg", "Valve with actuator.", interface="structural"),
        ],
        interface_checklist=[
            I(
                "Instrument air",
                "ic",
                "fluid",
                "Air consumption and supply pressure are in the instrument air balance.",
            ),
            I(
                "Signals",
                "ic",
                "control",
                "Control and feedback signals, fail state and solenoid supply are in the I/O list.",
            ),
            I(
                "Pipe support",
                "fluid",
                "structural",
                "Valve and actuator mass and moment arm are given to the pipe stress/support design.",
            ),
            I(
                "Noise",
                "fluid",
                "hse",
                "Predicted noise is below the area limit or a low-noise trim/insulation is specified.",
            ),
            I(
                "Access",
                "fluid",
                "civil",
                "Actuator removal height and handwheel access are respected in the layout.",
            ),
            I(
                "Electrical accessories",
                "ic",
                "electrical",
                "Solenoid, limit switch and positioner power supply and area certification are agreed.",
            ),
        ],
    )
)

_register(
    Template(
        key="power_transformer",
        name="Power transformer",
        discipline="electrical",
        description="Oil-immersed or dry-type power transformer.",
        standards_refs=[
            "IEC 60076-1",
            "IEC 60076-2",
            "IEC 60076-3",
            "IEC 60076-5",
            "IEC 60076-10",
            "IEC 60076-11",
            "IEEE C57.12.00",
            "IEC 60296",
        ],
        parameters=[
            P("Rated power", "kVA", "Rated power per cooling stage (ONAN/ONAF)."),
            P("Primary voltage", "kV", "Rated HV voltage."),
            P("Secondary voltage", "kV", "Rated LV voltage at no load."),
            P("Frequency", "Hz", "Rated frequency."),
            P("Vector group", None, "Winding connection (e.g. Dyn11)."),
            P("Impedance voltage", "%", "Short-circuit impedance at rated power and principal tap."),
            P("Tap changer", None, "Off-circuit or on-load, range and steps.", required=False),
            P("Cooling type", None, "ONAN / ONAF / AN / AF."),
            P("Insulation class / type", None, "Oil-immersed (mineral/ester) or dry-type cast resin."),
            P("Winding temperature rise", "K", "Average winding temperature rise."),
            P("No-load losses", "W", "Guaranteed no-load losses (Ecodesign tier).", interface="hvac"),
            P("Load losses", "W", "Guaranteed load losses at 75 degC.", interface="hvac"),
            P("Sound power level", "dB(A)", "Per IEC 60076-10.", interface="hse"),
            P("Ambient temperature", "degC", "Maximum design ambient."),
            P("Altitude", "m", "Site altitude for derating.", required=False),
            P("Insulation levels", "kV", "Lightning impulse / power frequency withstand per winding."),
            P("HV terminal arrangement", None, "Cable box, bushings or busduct.", interface="electrical"),
            P("LV terminal arrangement", None, "Cable box or busduct.", interface="electrical"),
            P("Total mass", "kg", "Transport and installed mass.", interface="structural"),
            P("Oil quantity", "L", "For bund sizing (oil-immersed).", required=False, interface="civil"),
            P(
                "Protection devices",
                None,
                "Buchholz, pressure relief, winding temperature indicator.",
                interface="ic",
            ),
            P("Short-circuit withstand", "s", "Thermal and dynamic withstand duration per IEC 60076-5."),
        ],
        interface_checklist=[
            I(
                "Losses vs ventilation",
                "electrical",
                "hvac",
                "No-load plus load losses at maximum loading set the transformer room ventilation "
                "or cooling.",
            ),
            I(
                "Mass vs foundation",
                "electrical",
                "structural",
                "Transport and installed mass, wheel/skid loads and jacking points are given to the "
                "foundation design.",
            ),
            I(
                "Oil containment",
                "electrical",
                "civil",
                "Bund volume covers the full oil quantity plus firefighting water where required.",
            ),
            I(
                "Fire separation",
                "electrical",
                "civil",
                "Separation distances or fire walls per the insulating liquid class are in the layout.",
            ),
            I(
                "Protection signals",
                "electrical",
                "ic",
                "Trip and alarm contacts (Buchholz, WTI, OTI, PRD) are in the protection and SCADA I/O list.",
            ),
            I(
                "Noise",
                "electrical",
                "hse",
                "Sound power level meets the site boundary limit with the chosen location and enclosure.",
            ),
            I(
                "Cable entries",
                "electrical",
                "civil",
                "Cable trench/duct routing and cable box orientation match the civil drawings.",
            ),
        ],
    )
)

_register(
    Template(
        key="lv_switchgear",
        name="LV switchgear / MCC",
        discipline="electrical",
        description="Low-voltage power switchgear and controlgear assembly (motor control centre).",
        standards_refs=[
            "IEC 61439-1",
            "IEC 61439-2",
            "IEC 60947-2",
            "IEC 60947-4-1",
            "IEC 61641",
            "IEC 60529",
            "IEC 60909-0",
        ],
        parameters=[
            P("Rated voltage", "V", "Rated operational voltage."),
            P("Frequency", "Hz", "Rated frequency."),
            P("Rated current of main busbar", "A", "Rated current InA."),
            P("Rated short-time withstand current", "kA", "Icw for 1 s."),
            P("Rated peak withstand current", "kA", "Ipk."),
            P("Form of internal separation", None, "Form 1 to 4b per IEC 61439-2."),
            P("Degree of protection", None, "IP rating of enclosure."),
            P(
                "Incomer type and rating",
                "A",
                "ACB/MCCB rating and number of incomers.",
                interface="electrical",
            ),
            P(
                "Outgoing feeders",
                None,
                "Feeder schedule: load, rating, starter type.",
                interface="mechanical",
            ),
            P("Internal arc classification", None, "IEC 61641 arcing class and duration.", required=False),
            P("Earthing system", None, "TN-S / TN-C-S / IT.", interface="electrical"),
            P("Control voltage", "V", "Auxiliary control supply.", interface="ic"),
            P(
                "Metering and communications",
                None,
                "Protocol (Modbus TCP, IEC 61850, Profinet).",
                interface="ic",
            ),
            P("Heat dissipation", "W", "Total losses at design load for room cooling.", interface="hvac"),
            P("Ambient temperature", "degC", "Design ambient inside the room."),
            P("Dimensions", "mm", "Overall width x depth x height.", interface="civil"),
            P("Mass", "kg", "Per section and total.", interface="structural"),
            P("Cable entry", None, "Top/bottom, gland plate arrangement.", interface="civil"),
            P("Spare capacity", "%", "Spare ways and busbar margin.", required=False),
        ],
        interface_checklist=[
            I(
                "Load list",
                "mechanical",
                "electrical",
                "Every motor and heater in the equipment list has a feeder of adequate rating and "
                "starter type.",
            ),
            I(
                "Heat load",
                "electrical",
                "hvac",
                "Switchgear and VSD losses are included in the electrical room cooling load.",
            ),
            I(
                "Floor loading",
                "electrical",
                "structural",
                "Section mass and plinth/base frame details are given to the floor design.",
            ),
            I(
                "Cable routing",
                "electrical",
                "civil",
                "Trench, floor cut-outs and gland plate positions match the civil layout.",
            ),
            I(
                "Control interfaces",
                "electrical",
                "ic",
                "Start/stop, status, fault and measurement signals per feeder are in the I/O list.",
            ),
            I(
                "Arc flash / egress",
                "electrical",
                "hse",
                "Arc flash boundary, escape routes and door swing are respected in the room layout.",
            ),
        ],
    )
)

_register(
    Template(
        key="pressure_vessel",
        name="Pressure vessel",
        discipline="mechanical",
        description="Unfired pressure vessel (separator, receiver, drum, column shell).",
        standards_refs=[
            "ASME BPVC Section VIII Div. 1",
            "EN 13445-3",
            "PED 2014/68/EU",
            "ASME B16.5",
            "NACE MR0175 / ISO 15156 (sour service)",
            "ASME PCC-2",
        ],
        parameters=[
            P("Service / contents", None, "Process fluid, phase and hazard classification."),
            P("Design pressure", "bar(g)", "Internal design pressure."),
            P("External design pressure", "bar(g)", "Vacuum or jacket pressure.", required=False),
            P("Design temperature", "degC", "Maximum design temperature."),
            P("Minimum design metal temperature", "degC", "MDMT for impact testing."),
            P("Operating pressure", "bar(g)", "Normal operating pressure."),
            P("Operating temperature", "degC", "Normal operating temperature."),
            P("Volume", "m3", "Geometric volume."),
            P("Inside diameter", "mm", "Shell inside diameter."),
            P("Tan-to-tan length", "mm", "Shell length."),
            P("Orientation", None, "Horizontal / vertical, support type (saddles/skirt/legs)."),
            P("Shell and head material", None, "Material grade (e.g. SA-516 Gr 70)."),
            P("Corrosion allowance", "mm", "Internal corrosion allowance."),
            P("Joint efficiency / NDE", None, "Radiography extent and joint efficiency."),
            P("Nozzle schedule", None, "Size, rating, service of every nozzle.", interface="fluid"),
            P("PWHT", None, "Post-weld heat treatment requirement.", required=False),
            P("Insulation", "mm", "Insulation type and thickness.", required=False, interface="mechanical"),
            P("Empty mass", "kg", "Fabricated mass.", interface="structural"),
            P("Operating mass", "kg", "Mass with contents.", interface="structural"),
            P("Hydrotest mass", "kg", "Mass filled with water.", interface="structural"),
            P("Wind / seismic data", None, "Site wind speed and seismic category.", interface="structural"),
            P("Relief device", None, "PSV set pressure and relieving case.", interface="fluid"),
            P("Instrument nozzles", None, "Level, pressure, temperature connections.", interface="ic"),
        ],
        interface_checklist=[
            I(
                "Mass vs foundation",
                "mechanical",
                "structural",
                "Empty, operating and hydrotest masses with support reactions are given to the "
                "foundation design.",
            ),
            I(
                "Nozzle loads",
                "mechanical",
                "fluid",
                "Allowable nozzle loads are agreed with the piping stress analysis.",
            ),
            I(
                "Relief",
                "mechanical",
                "fluid",
                "PSV capacity covers the governing case and the relief header is sized.",
            ),
            I(
                "Instrumentation",
                "mechanical",
                "ic",
                "Level and pressure instrument nozzles and standpipes match the instrument datasheets.",
            ),
            I(
                "Access",
                "mechanical",
                "civil",
                "Manway positions, platforms and ladders fit the plot plan and maintenance plan.",
            ),
            I(
                "Insulation / heat tracing",
                "mechanical",
                "electrical",
                "Heat tracing power and thermostats are in the electrical load list.",
            ),
        ],
    )
)

_register(
    Template(
        key="piping_system",
        name="Piping system",
        discipline="fluid",
        description="Process or utility piping system (one line class / service).",
        standards_refs=[
            "ASME B31.3",
            "EN 13480-3",
            "ASME B16.5",
            "ASME B16.9",
            "ASME B36.10M",
            "ASME B31.1 (power piping)",
            "ISO 15649",
        ],
        parameters=[
            P("Service", None, "Fluid service and category (normal / Category M / high pressure)."),
            P("Piping class", None, "Line class designation."),
            P("Design pressure", "bar(g)", "Design pressure of the line class."),
            P("Design temperature", "degC", "Maximum design temperature."),
            P("Minimum design temperature", "degC", "For impact testing and material selection."),
            P("Material", None, "Pipe material grade (e.g. ASTM A106 Gr B, A312 TP316L)."),
            P("Wall thickness / schedule", None, "Schedule per size."),
            P("Corrosion allowance", "mm", "Allowance for the service."),
            P("Flange rating", None, "ASME class / PN."),
            P("Nominal sizes", None, "Size range covered."),
            P("Velocity limit", "m/s", "Maximum fluid velocity.", required=False),
            P("Pressure drop allowance", "bar", "Allowable pressure drop for the line.", required=False),
            P("Insulation", "mm", "Type and thickness; personnel protection.", required=False),
            P(
                "Heat tracing",
                "W/m",
                "Electrical or steam tracing duty.",
                required=False,
                interface="electrical",
            ),
            P("Pressure test", "bar(g)", "Hydrotest pressure and medium."),
            P("NDE extent", "%", "Radiography / UT extent of welds."),
            P("Supports", None, "Support spacing and type.", interface="structural"),
            P(
                "Stress analysis criteria",
                None,
                "Lines requiring formal flexibility analysis.",
                interface="structural",
            ),
            P("Cleanliness / passivation", None, "Cleaning, pickling or passivation.", required=False),
        ],
        interface_checklist=[
            I(
                "Support loads",
                "fluid",
                "structural",
                "Pipe support reactions, anchor loads and thermal movements are given to the "
                "structure design.",
            ),
            I(
                "Equipment nozzle loads",
                "fluid",
                "mechanical",
                "Nozzle loads from stress analysis are within equipment allowables.",
            ),
            I(
                "Heat tracing",
                "fluid",
                "electrical",
                "Tracing power per circuit and thermostats are in the electrical load list.",
            ),
            I(
                "Instrument tie-ins",
                "fluid",
                "ic",
                "Instrument connections, straight-length requirements and orientation are agreed.",
            ),
            I(
                "Routing and access",
                "fluid",
                "civil",
                "Pipe racks, sleeves, penetrations and maintenance access are in the civil drawings.",
            ),
            I(
                "Relief and drains",
                "fluid",
                "hse",
                "Vents, drains and relief discharges go to safe locations.",
            ),
        ],
    )
)

_register(
    Template(
        key="structural_steel",
        name="Structural steel",
        discipline="structural",
        description="Structural steelwork for equipment support, pipe racks and platforms.",
        standards_refs=[
            "EN 1993-1-1",
            "EN 1993-1-8",
            "EN 1090-2",
            "AISC 360",
            "AISC 303",
            "ISO 12944",
            "EN 10025-2",
            "ISO 14122 (access)",
        ],
        parameters=[
            P("Structure type", None, "Pipe rack, equipment support, platform, building frame."),
            P("Design code", None, "Eurocode / AISC and national annex."),
            P("Steel grade", None, "Material grade (e.g. S355J2, A992)."),
            P("Execution class", None, "EN 1090-2 EXC class or AISC quality category."),
            P("Dead loads", "kN/m2", "Self weight and permanent loads."),
            P(
                "Equipment loads",
                "kN",
                "Operating, test and erection loads from equipment.",
                interface="mechanical",
            ),
            P("Live loads", "kN/m2", "Platform and access loads."),
            P("Piping loads", "kN", "Pipe support, anchor and friction loads.", interface="fluid"),
            P("Wind load", "m/s", "Basic wind speed or pressure."),
            P("Seismic parameters", None, "Zone, ground type, importance class."),
            P("Deflection limits", None, "Serviceability limits (L/x).", interface="mechanical"),
            P(
                "Vibration criteria",
                "Hz",
                "Natural frequency limits near rotating equipment.",
                interface="mechanical",
            ),
            P("Corrosion protection", None, "ISO 12944 category and paint system or galvanising."),
            P(
                "Fire protection",
                "min",
                "Fire resistance rating where required.",
                required=False,
                interface="hse",
            ),
            P("Bolt grade", None, "Bolt grade and preload requirements."),
            P("Welding", None, "Welding standard, consumables and NDE extent."),
            P(
                "Grating and handrail",
                None,
                "Grating type, handrail and kick plate standard.",
                required=False,
            ),
            P("Earthing provisions", None, "Earth bosses and bonding points.", interface="electrical"),
            P("Cable tray supports", None, "Cable tray/ladder support requirements.", interface="electrical"),
        ],
        interface_checklist=[
            I(
                "Equipment mass",
                "mechanical",
                "structural",
                "Every supported item's operating and test mass, anchor pattern and CoG are received "
                "before design freeze.",
            ),
            I(
                "Pipe loads",
                "fluid",
                "structural",
                "Support, anchor and friction loads from pipe stress analysis are applied.",
            ),
            I(
                "Vibration",
                "mechanical",
                "structural",
                "Rotating equipment frequencies are separated from structural natural frequencies.",
            ),
            I(
                "Cable routing",
                "electrical",
                "structural",
                "Tray supports, penetrations and earthing points are provided.",
            ),
            I(
                "Access",
                "hse",
                "structural",
                "Stairs, ladders and platforms meet ISO 14122 and the maintenance plan.",
            ),
            I("Fire", "hse", "structural", "Fire protection rating matches the fire hazard assessment."),
        ],
    )
)

_register(
    Template(
        key="hvac_ahu",
        name="HVAC air handling unit",
        discipline="mechanical",
        description="Packaged air handling unit with fans, coils, filters and controls.",
        standards_refs=[
            "EN 1886",
            "EN 13053",
            "ISO 16890",
            "EN 308",
            "ASHRAE 62.1",
            "ASHRAE 90.1",
            "ISO 5801",
            "Ecodesign (EU) 1253/2014",
        ],
        parameters=[
            P("Supply air flow", "m3/h", "Design supply air volume."),
            P("Return / extract air flow", "m3/h", "Design return air volume.", required=False),
            P("Fresh air fraction", "%", "Minimum outdoor air share."),
            P("External static pressure", "Pa", "Available pressure for ductwork."),
            P("Casing class", None, "EN 1886 mechanical strength, leakage, thermal transmittance class."),
            P("Filtration", None, "ISO 16890 filter classes per stage."),
            P("Cooling coil duty", "kW", "Total and sensible cooling.", interface="fluid"),
            P("Heating coil duty", "kW", "Heating capacity.", interface="fluid"),
            P("Chilled water conditions", "degC", "Inlet/outlet temperature and flow.", interface="fluid"),
            P("Heating medium conditions", "degC", "Inlet/outlet temperature and flow.", interface="fluid"),
            P("Supply air condition", "degC", "Dry bulb and humidity at outlet."),
            P("Heat recovery", "%", "Recovery type and dry efficiency per EN 308.", required=False),
            P("Humidifier", "kg/h", "Steam or adiabatic capacity.", required=False, interface="fluid"),
            P("Fan type and drive", None, "Plug fan, EC or VSD drive."),
            P("Fan motor power", "kW", "Absorbed and installed power.", interface="electrical"),
            P("Electrical supply", "V", "Voltage, phases, frequency.", interface="electrical"),
            P("Specific fan power", "W/(m3/s)", "SFP limit."),
            P("Sound power level", "dB(A)", "Breakout and in-duct levels.", interface="hse"),
            P("Dimensions", "mm", "Length x width x height.", interface="civil"),
            P("Operating mass", "kg", "Mass of complete unit.", interface="structural"),
            P("Controls", None, "BMS protocol (BACnet/Modbus), sensors, dampers.", interface="ic"),
            P("Condensate drain", None, "Drain size and trap.", interface="fluid"),
        ],
        interface_checklist=[
            I(
                "Electrical load",
                "mechanical",
                "electrical",
                "Fan motors, heaters and humidifier power are in the load list with starter type.",
            ),
            I(
                "Hydraulic",
                "mechanical",
                "fluid",
                "Coil flows and pressure drops are in the chilled/hot water network design.",
            ),
            I(
                "Mass vs structure",
                "mechanical",
                "structural",
                "Unit mass and point loads are given for the plant room floor or roof.",
            ),
            I(
                "Controls",
                "mechanical",
                "ic",
                "Sensor list, damper actuators and BMS points are in the I/O schedule.",
            ),
            I(
                "Acoustics",
                "mechanical",
                "hse",
                "Breakout and duct noise meet room criteria with attenuation specified.",
            ),
            I(
                "Access and drainage",
                "mechanical",
                "civil",
                "Service clearances, coil withdrawal space and drain routing are in the plant room layout.",
            ),
            I(
                "Outdoor air intake",
                "mechanical",
                "hse",
                "Intake location avoids exhausts and hazardous releases.",
            ),
        ],
    )
)


def list_templates() -> list[dict[str, Any]]:
    return [t.to_dict() for t in TEMPLATES.values()]


def get_template(key: str) -> Template | None:
    return TEMPLATES.get(key)
