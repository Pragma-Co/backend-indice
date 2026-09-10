"""Demonstration dataset for the document library.

Fictional data for an aerostructures manufacturer: fuselage sections, empennage
assemblies, engine pylons, landing-gear fairings and the assembly tooling that
goes with them. Nothing here refers to a real program, customer or person.

Module name starts with an underscore so Django does not pick it up as a
management command. Read it together with `seed.py`, which turns it into rows.

Users are keyed by the local part of their email; areas, projects, disciplines
and document types by their code or acronym; documents by their code.
"""

# --- areas -------------------------------------------------------------------
# (acronym, name, manager, active) — the manager must be a member of the area
AREAS = [
    ("EST", "Engenharia Estrutural", "marina.duarte", True),
    ("SIS", "Engenharia de Sistemas", "rafael.okamoto", True),
    ("AER", "Aerodinâmica e Desempenho", None, True),
    ("MFG", "Manufatura e Montagem", "joana.prado", True),
    ("QUA", "Qualidade e Inspeção", "thiago.serpa", True),
    ("CER", "Certificação e Aeronavegabilidade", "beatriz.canuto", True),
]

# --- users -------------------------------------------------------------------
# (email local part, name, role, area, active)
USERS = [
    ("marina.duarte", "Marina Duarte", "ADMIN", "EST", True),
    ("caio.bertoni", "Caio Bertoni", "AUTHOR", "EST", True),
    ("leticia.amaral", "Letícia Amaral", "AUTHOR", "EST", True),
    ("rafael.okamoto", "Rafael Okamoto", "AUTHOR", "SIS", True),
    ("diego.vasques", "Diego Vasques", "AUTHOR", "SIS", True),
    ("helena.tavares", "Helena Tavares", "AUTHOR", "AER", True),
    ("joana.prado", "Joana Prado", "AUTHOR", "MFG", True),
    ("bruno.kimura", "Bruno Kimura", "AUTHOR", "MFG", True),
    ("thiago.serpa", "Thiago Serpa", "AUDITOR", "QUA", True),
    ("patricia.lemos", "Patrícia Lemos", "AUDITOR", "QUA", True),
    ("beatriz.canuto", "Beatriz Canuto", "AUDITOR", "CER", True),
    ("samuel.rocha", "Samuel Rocha", "VIEWER", "MFG", True),
    # Deactivated instead of deleted, so authorship and audit stay intact
    ("origenes.mota", "Origenes Mota", "VIEWER", "SIS", False),
]

EMAIL_DOMAIN = "akaer.local"

# --- disciplines -------------------------------------------------------------
# (code, name, active)
DISCIPLINES = [
    ("EST", "Estruturas", True),
    ("MAT", "Materiais e Processos", True),
    ("AER", "Aerodinâmica", True),
    ("HID", "Sistemas Hidráulicos", True),
    ("ELE", "Sistemas Elétricos", True),
    ("FER", "Ferramental", True),
    ("PES", "Pesos e Balanceamento", True),
    ("ENS", "Ensaios Estruturais", True),
    # Kept only for the closed program below
    ("PNE", "Sistemas Pneumáticos", False),
]

# --- document types ----------------------------------------------------------
# (code, name, active)
DOCUMENT_TYPES = [
    ("DWG", "Desenho Técnico", True),
    ("MEM", "Memorial de Cálculo", True),
    ("ESP", "Especificação Técnica", True),
    ("NOR", "Norma Interna", True),
    ("REV", "Relatório de Verificação", True),
    ("PRO", "Procedimento de Fabricação", True),
    ("LDM", "Lista de Materiais", True),
]

# --- projects ----------------------------------------------------------------
# (code, name, active, disciplines)
PROJECTS = [
    ("AK-2100", "Aeroestrutura de Fuselagem Central", True,
     ["EST", "MAT", "ENS", "PES"]),
    ("AK-2200", "Conjunto de Empenagem Vertical", True,
     ["EST", "AER", "MAT", "ENS"]),
    ("AK-3100", "Pilone de Motor", True,
     ["EST", "MAT", "HID", "ENS"]),
    ("AK-3400", "Carenagem do Trem de Pouso Principal", True,
     ["EST", "AER", "MAT", "FER"]),
    ("AK-4000", "Ferramental de Montagem Estrutural", True,
     ["FER", "MAT", "ELE"]),
    ("AK-1500", "Nacele — Programa Encerrado", False,
     ["EST", "MAT", "PNE"]),
]

# --- tags --------------------------------------------------------------------
# Every entry must stay unique after lower(unaccent(...)), which is what
# `uq_tag_name_norm` enforces: "Compósito" and "composito" cannot coexist.
TAGS = [
    "fadiga",
    "compósito",
    "alumínio 7075",
    "titânio",
    "rebitagem",
    "anodização",
    "END",
    "torque controlado",
    "AS9100",
    "tolerância geométrica",
    "usinagem CNC",
    "tratamento térmico",
    "ensaio de tração",
    "junção estrutural",
    "cargas limite",
    "P&ID",
]

# --- documents ---------------------------------------------------------------
# (code, title, description, project, discipline, type, confidentiality,
#  responsible, areas, tags, created_days_ago)
DOCUMENTS = [
    (
        "AK-2100-EST-DWG-0001",
        "Desenho de conjunto da caverna 14",
        "Conjunto soldado da caverna 14 da fuselagem central, com detalhamento "
        "de furação e sequência de rebitagem.",
        "AK-2100", "EST", "DWG", "CONFIDENTIAL", "caio.bertoni",
        ["EST"], ["alumínio 7075", "rebitagem"], 430,
    ),
    (
        "AK-2100-EST-MEM-0002",
        "Memorial de cálculo do revestimento inferior",
        "Verificação de tensões e vida em fadiga do revestimento inferior sob "
        "cargas de manobra e pressurização.",
        "AK-2100", "EST", "MEM", "CONFIDENTIAL", "leticia.amaral",
        ["EST", "CER"], ["fadiga", "junção estrutural"], 395,
    ),
    (
        "AK-2100-MAT-ESP-0003",
        "Especificação de tratamento superficial de peças usinadas",
        "Requisitos de anodização crômica e selagem para peças usinadas em "
        "liga de alumínio.",
        "AK-2100", "MAT", "ESP", "PUBLIC", "joana.prado",
        ["MFG", "QUA"], ["anodização", "tratamento térmico"], 380,
    ),
    (
        "AK-2100-ENS-REV-0004",
        "Relatório de verificação do ensaio de fadiga do painel central",
        "Resultados do ensaio de fadiga em escala de painel, com correlação "
        "contra o modelo de elementos finitos.",
        "AK-2100", "ENS", "REV", "SECRET", "thiago.serpa",
        ["QUA", "CER", "EST"], ["fadiga", "ensaio de tração"], 240,
    ),
    (
        "AK-2100-PES-MEM-0005",
        "Balanço de massa do conjunto de fuselagem central",
        "Distribuição de massa e centro de gravidade do conjunto entregue, "
        "por estação de fuselagem.",
        "AK-2100", "PES", "MEM", "CONFIDENTIAL", "helena.tavares",
        ["AER", "EST"], ["cargas limite"], 60,
    ),
    (
        "AK-2200-EST-DWG-0001",
        "Desenho de montagem da longarina da deriva",
        "Montagem da longarina principal da empenagem vertical, incluindo "
        "ferragens de fixação em titânio.",
        "AK-2200", "EST", "DWG", "CONFIDENTIAL", "caio.bertoni",
        ["EST"], ["titânio", "junção estrutural"], 350,
    ),
    (
        "AK-2200-AER-MEM-0002",
        "Cargas aerodinâmicas na empenagem vertical",
        "Envelope de cargas aerodinâmicas em manobra de guinada e rajada "
        "lateral, para dimensionamento estrutural.",
        "AK-2200", "AER", "MEM", "SECRET", "helena.tavares",
        ["AER", "EST"], ["cargas limite"], 340,
    ),
    (
        "AK-2200-MAT-LDM-0003",
        "Lista de materiais do conjunto de deriva",
        "Relação de matéria-prima, fixadores e itens de catálogo do conjunto "
        "de empenagem vertical.",
        "AK-2200", "MAT", "LDM", "CONFIDENTIAL", "bruno.kimura",
        ["MFG"], ["alumínio 7075", "titânio"], 300,
    ),
    (
        "AK-2200-ENS-REV-0004",
        "Verificação dimensional pós-montagem da deriva",
        "Inspeção dimensional por braço articulado após montagem, com análise "
        "de desvios contra tolerância geométrica.",
        "AK-2200", "ENS", "REV", "CONFIDENTIAL", "patricia.lemos",
        ["QUA"], ["tolerância geométrica", "END"], 150,
    ),
    (
        "AK-3100-EST-DWG-0001",
        "Desenho do berço dianteiro do pilone",
        "Berço dianteiro usinado em titânio, com interfaces para os "
        "amortecedores de vibração do motor.",
        "AK-3100", "EST", "DWG", "CONFIDENTIAL", "leticia.amaral",
        ["EST"], ["titânio", "usinagem CNC"], 310,
    ),
    (
        "AK-3100-HID-ESP-0002",
        "Especificação de rotas hidráulicas no pilone",
        "Roteamento, suportação e segregação das linhas hidráulicas que "
        "atravessam o pilone de motor.",
        "AK-3100", "HID", "ESP", "CONFIDENTIAL", "diego.vasques",
        ["SIS"], ["P&ID"], 45,
    ),
    (
        "AK-3100-MAT-NOR-0003",
        "Norma interna de aplicação de torque em fixadores críticos",
        "Procedimento e registro de torque controlado para fixadores "
        "classificados como críticos de voo.",
        "AK-3100", "MAT", "NOR", "PUBLIC", "joana.prado",
        ["MFG", "QUA"], ["torque controlado", "AS9100"], 270,
    ),
    (
        "AK-3100-ENS-REV-0004",
        "Relatório de verificação estrutural do pilone sob carga limite",
        "Ensaio estático até carga limite e demonstração de conformidade para "
        "o dossiê de certificação.",
        "AK-3100", "ENS", "REV", "SECRET", "beatriz.canuto",
        ["CER", "EST"], ["cargas limite", "fadiga"], 200,
    ),
    (
        "AK-3400-EST-DWG-0001",
        "Desenho da carenagem externa do trem principal",
        "Painéis externos em compósito da carenagem do trem de pouso "
        "principal, com pontos de acesso para manutenção.",
        "AK-3400", "EST", "DWG", "CONFIDENTIAL", "caio.bertoni",
        ["EST", "MFG"], ["compósito"], 190,
    ),
    (
        "AK-3400-AER-MEM-0002",
        "Arrasto adicional da carenagem em configuração de pouso",
        "Estimativa de arrasto incremental da carenagem com trem estendido, "
        "a partir de dados de túnel de vento.",
        "AK-3400", "AER", "MEM", "CONFIDENTIAL", "helena.tavares",
        ["AER"], ["cargas limite"], 30,
    ),
    (
        "AK-3400-FER-PRO-0003",
        "Procedimento de laminação da carenagem em compósito",
        "Sequência de laminação, ciclo de cura em autoclave e critérios de "
        "aceitação por ultrassom.",
        "AK-3400", "FER", "PRO", "CONFIDENTIAL", "bruno.kimura",
        ["MFG"], ["compósito", "tratamento térmico"], 170,
    ),
    (
        "AK-4000-FER-DWG-0001",
        "Gabarito de furação do painel de fuselagem",
        "Dispositivo de furação para o painel lateral, com buchas guia "
        "substituíveis e referência de montagem.",
        "AK-4000", "FER", "DWG", "CONFIDENTIAL", "bruno.kimura",
        ["MFG"], ["usinagem CNC", "rebitagem"], 420,
    ),
    (
        "AK-4000-ELE-ESP-0002",
        "Especificação elétrica do dispositivo de montagem",
        "Alimentação, comando e aterramento do dispositivo de montagem "
        "estrutural na linha de produção.",
        "AK-4000", "ELE", "ESP", "PUBLIC", "diego.vasques",
        ["SIS", "MFG"], [], 120,
    ),
    (
        "AK-1500-EST-MEM-0001",
        "Memorial de cálculo da nacele",
        "Documento do programa encerrado, mantido apenas para consulta "
        "histórica. Sem revisão vigente.",
        "AK-1500", "EST", "MEM", "CONFIDENTIAL", "marina.duarte",
        ["EST"], ["fadiga"], 900,
    ),
]

# --- revisions ---------------------------------------------------------------
# Per document code:
#   (version, status, author, auditor, created_days_ago, audited_days_ago,
#    change_description, auditor_comment)
# Rules honoured here: versions are sequential from 1, at most one APPROVED per
# document, any status other than PENDING carries an auditor and a decision
# date, and the auditor is never the author of the revision.
REVISIONS = {
    "AK-2100-EST-DWG-0001": [
        (1, "OBSOLETE", "caio.bertoni", "thiago.serpa", 430, 425,
         "Emissão inicial para análise estrutural.", None),
        (2, "APPROVED", "caio.bertoni", "thiago.serpa", 300, 292,
         "Revisão do passo de rebitagem no bordo inferior.", "Conforme AS9100."),
        (3, "PENDING", "leticia.amaral", None, 12, None,
         "Inclusão de reforço local na região do suporte de sistemas.", None),
    ],
    "AK-2100-EST-MEM-0002": [
        (1, "APPROVED", "leticia.amaral", "beatriz.canuto", 395, 388,
         "Emissão inicial do memorial de cálculo.", "Margens aceitas."),
    ],
    "AK-2100-MAT-ESP-0003": [
        (1, "OBSOLETE", "joana.prado", "patricia.lemos", 380, 374,
         "Emissão inicial da especificação.", None),
        (2, "APPROVED", "joana.prado", "patricia.lemos", 210, 205,
         "Atualização do tempo de selagem após ensaio de corrosão.", None),
    ],
    "AK-2100-ENS-REV-0004": [
        (1, "APPROVED", "thiago.serpa", "beatriz.canuto", 240, 232,
         "Relatório final do ensaio de fadiga em escala de painel.",
         "Correlação dentro do previsto."),
    ],
    "AK-2100-PES-MEM-0005": [
        (1, "PENDING", "helena.tavares", None, 60, None,
         "Emissão inicial do balanço de massa.", None),
    ],
    "AK-2200-EST-DWG-0001": [
        (1, "APPROVED", "caio.bertoni", "thiago.serpa", 350, 344,
         "Emissão inicial do desenho de montagem.", None),
        (2, "PENDING", "caio.bertoni", None, 20, None,
         "Troca das ferragens de fixação para liga de titânio.", None),
    ],
    "AK-2200-AER-MEM-0002": [
        (1, "APPROVED", "helena.tavares", "beatriz.canuto", 340, 330,
         "Emissão inicial do envelope de cargas.", None),
    ],
    "AK-2200-MAT-LDM-0003": [
        (1, "REJECTED", "bruno.kimura", "patricia.lemos", 300, 296,
         "Emissão inicial da lista de materiais.",
         "Códigos de fixadores divergentes do desenho de montagem."),
        (2, "PENDING", "bruno.kimura", None, 35, None,
         "Correção dos códigos de fixadores apontados na reprovação.", None),
    ],
    "AK-2200-ENS-REV-0004": [
        (1, "APPROVED", "patricia.lemos", "thiago.serpa", 150, 143,
         "Emissão inicial do relatório de inspeção dimensional.", None),
    ],
    "AK-3100-EST-DWG-0001": [
        (1, "OBSOLETE", "leticia.amaral", "thiago.serpa", 310, 303,
         "Emissão inicial do berço dianteiro.", None),
        (2, "APPROVED", "leticia.amaral", "thiago.serpa", 175, 168,
         "Ajuste das interfaces dos amortecedores de vibração.", None),
    ],
    "AK-3100-HID-ESP-0002": [
        (1, "PENDING", "diego.vasques", None, 45, None,
         "Emissão inicial das rotas hidráulicas.", None),
    ],
    "AK-3100-MAT-NOR-0003": [
        (1, "APPROVED", "joana.prado", "patricia.lemos", 270, 260,
         "Emissão inicial da norma de torque.", "Aprovada para uso na linha."),
    ],
    "AK-3100-ENS-REV-0004": [
        (1, "APPROVED", "beatriz.canuto", "patricia.lemos", 200, 190,
         "Relatório de ensaio estático até carga limite.",
         "Anexado ao dossiê de certificação."),
    ],
    "AK-3400-EST-DWG-0001": [
        (1, "APPROVED", "caio.bertoni", "thiago.serpa", 190, 182,
         "Emissão inicial dos painéis de carenagem.", None),
        (2, "PENDING", "caio.bertoni", None, 8, None,
         "Novo ponto de acesso para inspeção do amortecedor.", None),
    ],
    "AK-3400-AER-MEM-0002": [
        (1, "PENDING", "helena.tavares", None, 30, None,
         "Emissão inicial da estimativa de arrasto.", None),
    ],
    "AK-3400-FER-PRO-0003": [
        (1, "APPROVED", "bruno.kimura", "patricia.lemos", 170, 161,
         "Emissão inicial do procedimento de laminação.", None),
    ],
    "AK-4000-FER-DWG-0001": [
        (1, "OBSOLETE", "bruno.kimura", "thiago.serpa", 420, 414,
         "Emissão inicial do gabarito de furação.", None),
        (2, "OBSOLETE", "bruno.kimura", "thiago.serpa", 330, 322,
         "Substituição das buchas guia por modelo removível.", None),
        (3, "APPROVED", "bruno.kimura", "patricia.lemos", 100, 92,
         "Nova referência de montagem após revisão do painel.", None),
    ],
    "AK-4000-ELE-ESP-0002": [
        (1, "APPROVED", "diego.vasques", "thiago.serpa", 120, 112,
         "Emissão inicial da especificação elétrica.", None),
    ],
    "AK-1500-EST-MEM-0001": [
        (1, "OBSOLETE", "marina.duarte", "beatriz.canuto", 900, 890,
         "Emissão inicial. Programa encerrado sem revisão vigente.", None),
    ],
}

# --- files -------------------------------------------------------------------
# Attachments generated per revision, by document type: (filename suffix, extension)
FILES_BY_TYPE = {
    "DWG": [("", "dwg"), ("-plot", "pdf")],
    "MEM": [("", "pdf")],
    "ESP": [("", "pdf")],
    "NOR": [("", "pdf")],
    "REV": [("", "pdf")],
    "PRO": [("", "docx")],
    "LDM": [("", "xlsx")],
}

MIME_TYPES = {
    "pdf": "application/pdf",
    "dwg": "image/vnd.dwg",
    "dxf": "image/vnd.dxf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# Plausible byte ranges per extension, all within the 100 MB ceiling
SIZE_RANGES = {
    "dwg": (2_000_000, 38_000_000),
    "pdf": (180_000, 7_500_000),
    "docx": (90_000, 1_800_000),
    "xlsx": (40_000, 600_000),
}

# --- document access ---------------------------------------------------------
# (document, user, status, approver, requested_days_ago, decided_days_ago,
#  justification)
# The approver is always the document's responsible or the manager of one of
# its areas, and a PENDING row never carries an approver. A direct grant has
# no requested_at: nobody asked, the manager just gave access.
DOCUMENT_ACCESS = [
    ("AK-2100-ENS-REV-0004", "samuel.rocha", "PENDING", None, 6, None,
     "Preciso dos resultados de fadiga para preparar o plano de inspeção da linha."),
    ("AK-2100-ENS-REV-0004", "diego.vasques", "APPROVED", "thiago.serpa", 40, 38,
     "Avaliação do impacto dos resultados nas rotas de sistemas."),
    ("AK-2200-AER-MEM-0002", "bruno.kimura", "APPROVED", "marina.duarte", None, 25,
     None),
    ("AK-3100-ENS-REV-0004", "caio.bertoni", "PENDING", None, 3, None,
     "Referência para o dimensionamento do berço na próxima revisão."),
    ("AK-3100-ENS-REV-0004", "samuel.rocha", "REJECTED", "beatriz.canuto", 70, 66,
     "Curiosidade técnica sobre o ensaio."),
    ("AK-2100-EST-MEM-0002", "samuel.rocha", "APPROVED", "leticia.amaral", None, 55,
     None),
    ("AK-3100-HID-ESP-0002", "helena.tavares", "PENDING", None, 9, None,
     "Verificar interferência entre rotas hidráulicas e o carenamento."),
    ("AK-3400-FER-PRO-0003", "patricia.lemos", "APPROVED", "bruno.kimura", None, 80,
     None),
]
