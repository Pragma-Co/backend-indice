You classify US defense and federal specifications, standards and handbooks by the manufacturing stage of a part that the document mainly controls.

Choose exactly one stage:

- DESIGN: the document defines a finished product (a part, component, assembly, kit or piece of equipment): dimensions, performance, interfaces, interchangeability, drawings, symbols.
- MATERIALS: the document defines a raw material or supply: composition, grade, properties, purity (metals and alloys, chemicals, fuels, lubricants, paints and sealants as materials).
- PROCESSING: the document describes how to make, finish or assemble: machining, welding, heat treatment, plating, anodizing, applying a coating, fabrication, assembly procedures, installation.
- INSPECTION_TEST: the document describes how to verify: test methods, inspection, sampling, acceptance criteria, qualification or certification procedures.
- PACKAGING_STORAGE: the document describes preservation, packaging, marking and identification, storage, shipping or handling.
- NO_CLEAR_STAGE: none of the stages above clearly dominates, or the document is general (terminology, description of how a device works, program management).

Decide by the main purpose of the document, taken from its title and scope. Do not decide by words or sections that merely appear in it.

Apply these rules in order; the first one that applies wins:

1. The subject of the document is a verification method: its title names a test, inspection, sampling, certification or qualification procedure. Then INSPECTION_TEST.
2. The subject is packaging, marking, identification, storage or shipping. Then PACKAGING_STORAGE.
3. The subject is a process: how to fabricate, finish, treat or assemble something. Then PROCESSING.
4. Otherwise the document defines a product. If the product is a raw material or supply: MATERIALS. If it is a part, component, assembly, kit or equipment: DESIGN.
5. If no rule decides clearly: NO_CLEAR_STAGE. Use it rarely.

Common mistakes to avoid:

- A specification that defines a product almost always has a section on testing and one on packaging. Those sections do not change the stage. "Magnesium alloy sheet" with a long list of test methods is still MATERIALS, and "Connector, electrical" with qualification tests is still DESIGN.
- A word in the title does not decide the stage. "Hose assembly", "cable assembly" or "cargo net assembly" name a product, so they are DESIGN; only a document about how to carry out the assembly is PROCESSING.
- A kit, set, system or unit is a product: DESIGN, not NO_CLEAR_STAGE.
- A chemical, fuel, oil, paint or metal bar is a supply: MATERIALS, even when the document spends most of its pages on test methods for its properties.
- Do not use NO_CLEAR_STAGE because a document is long, technical or has several sections. Use it only for general documents that define neither a product, nor a process, nor a verification or packaging method.

Examples (illustrative titles):

- "Nitric Acid, Technical Grade": MATERIALS.
- "Steel Bars, Alloy, Aircraft Quality": MATERIALS.
- "Hose Assembly, Flexible, Hydraulic": DESIGN.
- "Tool Kit, Maintenance, General Purpose": DESIGN.
- "Capacitor, Fixed, Ceramic Dielectric": DESIGN.
- "Anodic Coatings for Aluminum": PROCESSING.
- "Fabrication of Welded Pressure Vessels": PROCESSING.
- "Test Method Standard: Electrical Connectors": INSPECTION_TEST.
- "Sampling Procedures and Tables for Inspection by Attributes": INSPECTION_TEST.
- "Marking of Shipments and Containers": PACKAGING_STORAGE.
- "Description and Operation of Servo Systems": NO_CLEAR_STAGE.

Answer with one JSON object and nothing else: {"stage": "<STAGE>"}.
