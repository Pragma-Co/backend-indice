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
    ("COM", "Sistemas de Combustível", None, True),
    ("HID", "Sistemas Hidráulicos", None, True),
    ("INT", "Integração de Sistemas", None, True),
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
    ("renato.fontes", "Renato Fontes", "AUTHOR", "COM", True),
    ("luciana.maeda", "Luciana Maeda", "AUTHOR", "HID", True),
    ("andre.cardoso", "André Cardoso", "AUTHOR", "INT", True),
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
    ("ARM", "Armamento", True),
    ("MUN", "Munições e Pirotecnia", True),
    ("OPT", "Óptica e Controle de Tiro", True),
    ("NAV", "Sistemas Navais", True),
    ("RFE", "Radiofrequência", True),
    ("EMB", "Embalagens", True),
    ("COM", "Sistemas de Combustível", True),
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
    ("GPR", "Guia de Projeto", True),
    ("MMA", "Manual de Manutenção", True),
    ("RTE", "Relatório Técnico", True),
]

# --- projects ----------------------------------------------------------------
# (code, name, active)
PROJECTS = [
    ("AK-2100", "Aeroestrutura de Fuselagem Central", True),
    ("AK-2200", "Conjunto de Empenagem Vertical", True),
    ("AK-3100", "Pilone de Motor", True),
    ("AK-3400", "Carenagem do Trem de Pouso Principal", True),
    ("AK-4000", "Ferramental de Montagem Estrutural", True),
    ("AK-4100", "Armamentos e Munições", True),
    ("AK-4300", "Pontaria e Observação", True),
    ("AK-4400", "Equipamentos Auxiliares Navais", True),
    ("AK-4500", "Componentes Elétricos e Radiofrequência", True),
    ("AK-4600", "Embalagens Técnicas", True),
    ("AK-4700", "Materiais Têxteis e Auxiliares", True),
    ("AK-5100", "Sistema de Combustível", True),
    ("AK-5200", "Sistema Hidráulico", True),
    ("AK-5300", "Sistema de Controle de Voo", True),
    ("AK-5400", "Trem de Pouso", True),
    ("AK-1500", "Nacele — Programa Encerrado", False),
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
    "vazão de combustível",
    "hidráulica de alta pressão",
    "compatibilidade eletromagnética",
    "alinhamento óptico",
    "munição inerte",
    "embalagem",
    "vedação",
    "vibração",
]

# --- documents ---------------------------------------------------------------
# (code, title, description, project, discipline, type, confidentiality,
#  responsible, created_by, areas, tags, created_days_ago)
# The code is <project>-<discipline>-<type>-<sequence>: the sequence counts the
# documents sharing the same prefix in insertion order (0001, 0002, ...), so the
# older document of a prefix always comes first here.
# Visibility rules the data honours:
#   PUBLIC       - every user sees it.
#   CONFIDENTIAL - only the users of the document's areas (plus explicit grants);
#                  the areas always include those of the responsible, of every
#                  revision author and of every auditor.
#   SECRET       - only selected users: the responsible, the grants in
#                  DOCUMENT_ACCESS and the members of a matching access group.
# created_by is always the author of revision 1, as the creation flow does.
DOCUMENTS = [
    # --- AK-2100 -------------------------------------------------------------
    (
        "AK-2100-EST-DWG-0001",
        "Desenho de conjunto da caverna 14",
        "Conjunto soldado da caverna 14 da fuselagem central, com detalhamento de furação e "
        "sequência de rebitagem.",
        "AK-2100",
        "EST",
        "DWG",
        "CONFIDENTIAL",
        "caio.bertoni",
        "caio.bertoni",
        ["EST", "QUA"],
        ["alumínio 7075", "rebitagem"],
        430,
    ),
    (
        "AK-2100-EST-DWG-0002",
        "Desenho de conjunto da caverna 15",
        "Conjunto da caverna 15, vizinha à caverna 14, com a junção ao revestimento inferior.",
        "AK-2100",
        "EST",
        "DWG",
        "CONFIDENTIAL",
        "leticia.amaral",
        "leticia.amaral",
        ["EST", "QUA"],
        ["alumínio 7075", "junção estrutural"],
        280,
    ),
    (
        "AK-2100-EST-MEM-0001",
        "Memorial de cálculo do revestimento inferior",
        "Verificação de tensões e vida em fadiga do revestimento inferior sob cargas de manobra e "
        "pressurização.",
        "AK-2100",
        "EST",
        "MEM",
        "CONFIDENTIAL",
        "leticia.amaral",
        "leticia.amaral",
        ["EST", "CER"],
        ["fadiga", "junção estrutural"],
        395,
    ),
    (
        "AK-2100-EST-MEM-0002",
        "Memorial de cálculo das cavernas 14 e 15",
        "Dimensionamento das cavernas 14 e 15 para as cargas limite e verificação de fadiga nas "
        "junções.",
        "AK-2100",
        "EST",
        "MEM",
        "CONFIDENTIAL",
        "caio.bertoni",
        "caio.bertoni",
        ["EST", "CER"],
        ["fadiga", "junção estrutural", "cargas limite"],
        150,
    ),
    (
        "AK-2100-MAT-ESP-0001",
        "Especificação de tratamento superficial de peças usinadas",
        "Requisitos de anodização crômica e selagem para peças usinadas em liga de alumínio.",
        "AK-2100",
        "MAT",
        "ESP",
        "PUBLIC",
        "joana.prado",
        "joana.prado",
        ["MFG", "QUA"],
        ["anodização", "tratamento térmico"],
        380,
    ),
    (
        "AK-2100-MAT-ESP-0002",
        "Especificação de pintura e selagem da superfície externa",
        "Sistema de pintura, espessuras e critérios de aceitação para a superfície externa da "
        "fuselagem.",
        "AK-2100",
        "MAT",
        "ESP",
        "PUBLIC",
        "joana.prado",
        "bruno.kimura",
        ["MFG", "QUA"],
        ["anodização"],
        120,
    ),
    (
        "AK-2100-MAT-PRO-0001",
        "Procedimento de anodização crômica",
        "Passo a passo do banho de anodização crômica, controle de concentração e inspeção final.",
        "AK-2100",
        "MAT",
        "PRO",
        "PUBLIC",
        "joana.prado",
        "joana.prado",
        ["MFG", "QUA"],
        ["anodização", "tratamento térmico"],
        90,
    ),
    (
        "AK-2100-ENS-REV-0001",
        "Relatório de verificação do ensaio de fadiga do painel central",
        "Resultados do ensaio de fadiga em escala de painel, com correlação contra o modelo de "
        "elementos finitos.",
        "AK-2100",
        "ENS",
        "REV",
        "SECRET",
        "thiago.serpa",
        "thiago.serpa",
        ["QUA", "CER", "EST"],
        ["fadiga", "ensaio de tração"],
        240,
    ),
    (
        "AK-2100-PES-MEM-0001",
        "Balanço de massa do conjunto de fuselagem central",
        "Distribuição de massa e centro de gravidade do conjunto entregue, por estação de "
        "fuselagem.",
        "AK-2100",
        "PES",
        "MEM",
        "CONFIDENTIAL",
        "helena.tavares",
        "helena.tavares",
        ["AER", "EST"],
        ["cargas limite"],
        60,
    ),
    # --- AK-2200 -------------------------------------------------------------
    (
        "AK-2200-EST-DWG-0001",
        "Desenho de montagem da longarina da deriva",
        "Montagem da longarina principal da empenagem vertical, incluindo ferragens de fixação em "
        "titânio.",
        "AK-2200",
        "EST",
        "DWG",
        "CONFIDENTIAL",
        "caio.bertoni",
        "caio.bertoni",
        ["EST", "QUA"],
        ["titânio", "junção estrutural"],
        350,
    ),
    (
        "AK-2200-AER-MEM-0001",
        "Cargas aerodinâmicas na empenagem vertical",
        "Envelope de cargas aerodinâmicas em manobra de guinada e rajada lateral, para "
        "dimensionamento estrutural.",
        "AK-2200",
        "AER",
        "MEM",
        "SECRET",
        "helena.tavares",
        "helena.tavares",
        ["AER", "EST", "CER"],
        ["cargas limite"],
        340,
    ),
    (
        "AK-2200-MAT-LDM-0001",
        "Lista de materiais do conjunto de deriva",
        "Relação de matéria-prima, fixadores e itens de catálogo do conjunto de empenagem "
        "vertical.",
        "AK-2200",
        "MAT",
        "LDM",
        "CONFIDENTIAL",
        "bruno.kimura",
        "bruno.kimura",
        ["MFG", "QUA"],
        ["alumínio 7075", "titânio"],
        300,
    ),
    (
        "AK-2200-ENS-REV-0001",
        "Verificação dimensional pós-montagem da deriva",
        "Inspeção dimensional por braço articulado após montagem, com análise de desvios contra "
        "tolerância geométrica.",
        "AK-2200",
        "ENS",
        "REV",
        "CONFIDENTIAL",
        "patricia.lemos",
        "patricia.lemos",
        ["QUA"],
        ["tolerância geométrica", "END"],
        150,
    ),
    (
        "AK-2200-ENS-REV-0002",
        "Verificação dimensional da longarina após tratamento térmico",
        "Medição da longarina da deriva depois do tratamento térmico, para detectar empenamento "
        "residual.",
        "AK-2200",
        "ENS",
        "REV",
        "CONFIDENTIAL",
        "thiago.serpa",
        "thiago.serpa",
        ["QUA", "MFG"],
        ["tolerância geométrica", "tratamento térmico"],
        70,
    ),
    # --- AK-3100 -------------------------------------------------------------
    (
        "AK-3100-EST-DWG-0001",
        "Desenho do berço dianteiro do pilone",
        "Berço dianteiro usinado em titânio, com interfaces para os amortecedores de vibração do "
        "motor.",
        "AK-3100",
        "EST",
        "DWG",
        "CONFIDENTIAL",
        "leticia.amaral",
        "leticia.amaral",
        ["EST", "QUA"],
        ["titânio", "usinagem CNC", "vibração"],
        310,
    ),
    (
        "AK-3100-HID-ESP-0001",
        "Especificação de rotas hidráulicas no pilone",
        "Roteamento, suportação e segregação das linhas hidráulicas que atravessam o pilone de "
        "motor.",
        "AK-3100",
        "HID",
        "ESP",
        "CONFIDENTIAL",
        "diego.vasques",
        "diego.vasques",
        ["SIS", "HID"],
        ["P&ID"],
        45,
    ),
    (
        "AK-3100-MAT-NOR-0001",
        "Norma interna de aplicação de torque em fixadores críticos",
        "Procedimento e registro de torque controlado para fixadores classificados como críticos "
        "de voo.",
        "AK-3100",
        "MAT",
        "NOR",
        "PUBLIC",
        "joana.prado",
        "joana.prado",
        ["MFG", "QUA"],
        ["torque controlado", "AS9100"],
        270,
    ),
    (
        "AK-3100-MAT-NOR-0002",
        "Norma interna de rastreabilidade de fixadores",
        "Identificação, lote e rastreabilidade dos fixadores desde o recebimento até a montagem.",
        "AK-3100",
        "MAT",
        "NOR",
        "PUBLIC",
        "joana.prado",
        "joana.prado",
        ["MFG", "QUA"],
        ["AS9100", "torque controlado"],
        100,
    ),
    (
        "AK-3100-ENS-REV-0001",
        "Relatório de verificação estrutural do pilone sob carga limite",
        "Ensaio estático até carga limite e demonstração de conformidade para o dossiê de "
        "certificação.",
        "AK-3100",
        "ENS",
        "REV",
        "SECRET",
        "beatriz.canuto",
        "beatriz.canuto",
        ["CER", "EST", "QUA"],
        ["cargas limite", "fadiga"],
        200,
    ),
    # --- AK-3400 -------------------------------------------------------------
    (
        "AK-3400-EST-DWG-0001",
        "Desenho da carenagem externa do trem principal",
        "Painéis externos em compósito da carenagem do trem de pouso principal, com pontos de "
        "acesso para manutenção.",
        "AK-3400",
        "EST",
        "DWG",
        "CONFIDENTIAL",
        "caio.bertoni",
        "caio.bertoni",
        ["EST", "MFG", "QUA"],
        ["compósito"],
        190,
    ),
    (
        "AK-3400-AER-MEM-0001",
        "Arrasto adicional da carenagem em configuração de pouso",
        "Estimativa de arrasto incremental da carenagem com trem estendido, a partir de dados de "
        "túnel de vento.",
        "AK-3400",
        "AER",
        "MEM",
        "CONFIDENTIAL",
        "helena.tavares",
        "helena.tavares",
        ["AER", "EST"],
        ["cargas limite"],
        30,
    ),
    (
        "AK-3400-FER-PRO-0001",
        "Procedimento de laminação da carenagem em compósito",
        "Sequência de laminação, ciclo de cura em autoclave e critérios de aceitação por "
        "ultrassom.",
        "AK-3400",
        "FER",
        "PRO",
        "CONFIDENTIAL",
        "bruno.kimura",
        "bruno.kimura",
        ["MFG", "QUA"],
        ["compósito", "tratamento térmico"],
        170,
    ),
    # --- AK-4000 -------------------------------------------------------------
    (
        "AK-4000-FER-DWG-0001",
        "Gabarito de furação do painel de fuselagem",
        "Dispositivo de furação para o painel lateral, com buchas guia substituíveis e referência "
        "de montagem.",
        "AK-4000",
        "FER",
        "DWG",
        "CONFIDENTIAL",
        "bruno.kimura",
        "bruno.kimura",
        ["MFG", "QUA"],
        ["usinagem CNC", "rebitagem"],
        420,
    ),
    (
        "AK-4000-FER-DWG-0002",
        "Gabarito de furação do painel da empenagem",
        "Dispositivo de furação para o painel da empenagem vertical, derivado do gabarito da "
        "fuselagem.",
        "AK-4000",
        "FER",
        "DWG",
        "CONFIDENTIAL",
        "bruno.kimura",
        "bruno.kimura",
        ["MFG", "QUA"],
        ["usinagem CNC", "rebitagem"],
        260,
    ),
    (
        "AK-4000-FER-GPR-0001",
        "Guia de projeto de gabaritos de furação",
        "Critérios de projeto, materiais e tolerâncias para gabaritos de furação usados na "
        "montagem estrutural.",
        "AK-4000",
        "FER",
        "GPR",
        "PUBLIC",
        "bruno.kimura",
        "bruno.kimura",
        ["MFG", "QUA", "EST"],
        ["usinagem CNC", "tolerância geométrica"],
        200,
    ),
    (
        "AK-4000-ELE-ESP-0001",
        "Especificação elétrica do dispositivo de montagem",
        "Alimentação, comando e aterramento do dispositivo de montagem estrutural na linha de "
        "produção.",
        "AK-4000",
        "ELE",
        "ESP",
        "PUBLIC",
        "diego.vasques",
        "diego.vasques",
        ["SIS", "MFG", "QUA"],
        [],
        120,
    ),
    # --- AK-4100 / AK-4300 / AK-4500 / AK-4600 ---------------------------------
    (
        "AK-4100-ARM-ESP-0001",
        "Especificação de integração de armamento ao pilone",
        "Interfaces mecânicas e elétricas para a integração do armamento ao pilone, com limites "
        "de carga.",
        "AK-4100",
        "ARM",
        "ESP",
        "SECRET",
        "rafael.okamoto",
        "rafael.okamoto",
        ["SIS", "CER"],
        ["cargas limite"],
        160,
    ),
    (
        "AK-4100-MUN-REV-0001",
        "Relatório de verificação de segurança de munições inertes",
        "Resultados da verificação de segurança no manuseio e armazenagem de munições inertes de "
        "ensaio.",
        "AK-4100",
        "MUN",
        "REV",
        "SECRET",
        "thiago.serpa",
        "patricia.lemos",
        ["QUA", "CER"],
        ["munição inerte", "END"],
        110,
    ),
    (
        "AK-4300-OPT-MEM-0001",
        "Memorial de alinhamento do sistema de pontaria",
        "Cadeia de tolerâncias e procedimento de boresight do sistema de pontaria.",
        "AK-4300",
        "OPT",
        "MEM",
        "SECRET",
        "diego.vasques",
        "diego.vasques",
        ["SIS", "QUA"],
        ["alinhamento óptico", "tolerância geométrica"],
        85,
    ),
    (
        "AK-4500-RFE-RTE-0001",
        "Relatório de compatibilidade eletromagnética do chicote",
        "Ensaios de emissão e suscetibilidade do chicote de radiofrequência instalado.",
        "AK-4500",
        "RFE",
        "RTE",
        "CONFIDENTIAL",
        "diego.vasques",
        "diego.vasques",
        ["SIS", "QUA"],
        ["compatibilidade eletromagnética"],
        75,
    ),
    (
        "AK-4600-EMB-NOR-0001",
        "Norma interna de embalagem de peças usinadas",
        "Requisitos de proteção, amortecimento e identificação para o transporte de peças "
        "usinadas.",
        "AK-4600",
        "EMB",
        "NOR",
        "PUBLIC",
        "bruno.kimura",
        "bruno.kimura",
        ["MFG", "QUA"],
        ["embalagem"],
        140,
    ),
    # --- AK-5100 / AK-5200 / AK-5300 / AK-5400 ---------------------------------
    (
        "AK-5100-COM-ESP-0001",
        "Especificação do tanque integral de combustível",
        "Requisitos de estanqueidade, selagem e ensaio do tanque integral de combustível da asa.",
        "AK-5100",
        "COM",
        "ESP",
        "CONFIDENTIAL",
        "renato.fontes",
        "renato.fontes",
        ["COM", "QUA"],
        ["vedação", "vazão de combustível"],
        220,
    ),
    (
        "AK-5100-COM-MEM-0001",
        "Memorial de cálculo da vazão do sistema de transferência de combustível",
        "Dimensionamento das bombas e linhas de transferência entre tanques.",
        "AK-5100",
        "COM",
        "MEM",
        "CONFIDENTIAL",
        "renato.fontes",
        "renato.fontes",
        ["COM", "SIS", "QUA"],
        ["vazão de combustível"],
        130,
    ),
    (
        "AK-5200-HID-ESP-0001",
        "Especificação do atuador hidráulico do flape",
        "Requisitos de pressão, curso e vedação do atuador hidráulico do flape.",
        "AK-5200",
        "HID",
        "ESP",
        "CONFIDENTIAL",
        "luciana.maeda",
        "luciana.maeda",
        ["HID", "QUA"],
        ["hidráulica de alta pressão", "vedação"],
        210,
    ),
    (
        "AK-5200-HID-DWG-0001",
        "Desenho de instalação da central hidráulica",
        "Instalação da central hidráulica na fuselagem, com suportação e conexões das linhas.",
        "AK-5200",
        "HID",
        "DWG",
        "CONFIDENTIAL",
        "luciana.maeda",
        "luciana.maeda",
        ["HID", "SIS", "QUA"],
        ["hidráulica de alta pressão", "P&ID"],
        95,
    ),
    (
        "AK-5200-HID-GPR-0001",
        "Guia de identificação de linhas hidráulicas",
        "Código de cores, marcações e etiquetas das linhas hidráulicas de aeronave.",
        "AK-5200",
        "HID",
        "GPR",
        "PUBLIC",
        "luciana.maeda",
        "luciana.maeda",
        ["HID", "QUA"],
        ["P&ID"],
        50,
    ),
    (
        "AK-5300-ELE-ESP-0001",
        "Especificação elétrica do módulo de controle de voo",
        "Alimentação, redundância e interfaces do módulo do sistema de controle de voo.",
        "AK-5300",
        "ELE",
        "ESP",
        "CONFIDENTIAL",
        "andre.cardoso",
        "andre.cardoso",
        ["INT", "SIS", "QUA"],
        ["compatibilidade eletromagnética"],
        180,
    ),
    (
        "AK-5400-EST-DWG-0001",
        "Desenho do cilindro principal do trem de pouso",
        "Cilindro principal em aço de alta resistência, com interfaces para o amortecedor.",
        "AK-5400",
        "EST",
        "DWG",
        "CONFIDENTIAL",
        "leticia.amaral",
        "leticia.amaral",
        ["EST", "HID", "QUA"],
        ["usinagem CNC", "vedação"],
        140,
    ),
    # --- recent documents (last 30 days) ---------------------------------------
    (
        "AK-2200-EST-MEM-0001",
        "Memorial de cálculo da longarina da deriva",
        "Dimensionamento da longarina principal da deriva para as cargas aerodinâmicas de manobra.",
        "AK-2200",
        "EST",
        "MEM",
        "CONFIDENTIAL",
        "leticia.amaral",
        "leticia.amaral",
        ["EST", "CER"],
        ["fadiga", "cargas limite"],
        18,
    ),
    (
        "AK-4600-EMB-NOR-0002",
        "Norma interna de embalagem de componentes eletrônicos sensíveis",
        "Proteção antiestática e controle de umidade no transporte de componentes eletrônicos.",
        "AK-4600",
        "EMB",
        "NOR",
        "PUBLIC",
        "bruno.kimura",
        "bruno.kimura",
        ["MFG", "QUA"],
        ["embalagem"],
        25,
    ),
    (
        "AK-3400-EST-DWG-0002",
        "Desenho do painel de acesso da carenagem",
        "Painel removível da carenagem do trem principal, com fixadores de um quarto de volta.",
        "AK-3400",
        "EST",
        "DWG",
        "CONFIDENTIAL",
        "caio.bertoni",
        "caio.bertoni",
        ["EST", "MFG", "QUA"],
        ["compósito"],
        5,
    ),
    (
        "AK-5300-ELE-ESP-0002",
        "Especificação de redundância do barramento de dados de voo",
        "Topologia redundante, tempos de resposta e falhas toleradas no barramento de dados.",
        "AK-5300",
        "ELE",
        "ESP",
        "CONFIDENTIAL",
        "andre.cardoso",
        "andre.cardoso",
        ["INT", "SIS", "QUA"],
        ["compatibilidade eletromagnética"],
        3,
    ),
    # --- AK-1500 (closed program) -----------------------------------------------
    (
        "AK-1500-EST-MEM-0001",
        "Memorial de cálculo da nacele",
        "Documento do programa encerrado, mantido apenas para consulta histórica. Sem revisão "
        "vigente.",
        "AK-1500",
        "EST",
        "MEM",
        "CONFIDENTIAL",
        "marina.duarte",
        "marina.duarte",
        ["EST", "CER"],
        ["fadiga"],
        900,
    ),
]

# --- revisions ---------------------------------------------------------------
# Per document code:
#   (version, status, author, auditor, created_days_ago, audited_days_ago,
#    change_description, auditor_comment)
# Rules honoured here: versions are sequential from 1, version 1 is created with
# the document, any status other than PENDING carries an auditor and a decision
# date, the auditor is never the author nor the document's responsible, and a
# justification, when present, has at least 20 characters.
REVISIONS = {
    "AK-2100-EST-DWG-0001": [
        (
            1,
            "APPROVED",
            "caio.bertoni",
            "thiago.serpa",
            430,
            425,
            "Emissão inicial para análise estrutural.",
            None,
        ),
        (
            2,
            "APPROVED",
            "caio.bertoni",
            "thiago.serpa",
            300,
            292,
            "Revisão do passo de rebitagem no bordo inferior.",
            "Passo de rebitagem conforme AS9100.",
        ),
        (
            3,
            "PENDING",
            "leticia.amaral",
            None,
            12,
            None,
            "Inclusão de reforço local na região do suporte de sistemas.",
            None,
        ),
    ],
    "AK-2100-EST-DWG-0002": [
        (
            1,
            "APPROVED",
            "leticia.amaral",
            "thiago.serpa",
            280,
            272,
            "Emissão inicial da caverna 15.",
            None,
        ),
    ],
    "AK-2100-EST-MEM-0001": [
        (
            1,
            "APPROVED",
            "leticia.amaral",
            "beatriz.canuto",
            395,
            388,
            "Emissão inicial do memorial de cálculo.",
            "Margens de segurança aceitas para as cargas limite.",
        ),
    ],
    "AK-2100-EST-MEM-0002": [
        (
            1,
            "APPROVED",
            "caio.bertoni",
            "beatriz.canuto",
            150,
            141,
            "Emissão inicial do dimensionamento das cavernas.",
            None,
        ),
        (
            2,
            "PENDING",
            "leticia.amaral",
            None,
            10,
            None,
            "Atualização das cargas após revisão do desenho da caverna 14.",
            None,
        ),
    ],
    "AK-2100-MAT-ESP-0001": [
        (
            1,
            "APPROVED",
            "joana.prado",
            "patricia.lemos",
            380,
            374,
            "Emissão inicial da especificação.",
            None,
        ),
        (
            2,
            "APPROVED",
            "joana.prado",
            "patricia.lemos",
            210,
            205,
            "Atualização do tempo de selagem após ensaio de corrosão.",
            None,
        ),
    ],
    "AK-2100-MAT-ESP-0002": [
        (
            1,
            "APPROVED",
            "bruno.kimura",
            "thiago.serpa",
            120,
            113,
            "Emissão inicial da especificação de pintura.",
            None,
        ),
    ],
    "AK-2100-MAT-PRO-0001": [
        (
            1,
            "APPROVED",
            "joana.prado",
            "patricia.lemos",
            90,
            84,
            "Emissão inicial do procedimento de anodização.",
            None,
        ),
    ],
    "AK-2100-ENS-REV-0001": [
        (
            1,
            "APPROVED",
            "thiago.serpa",
            "beatriz.canuto",
            240,
            232,
            "Relatório final do ensaio de fadiga em escala de painel.",
            "Correlação dentro do previsto pelo modelo.",
        ),
    ],
    "AK-2100-PES-MEM-0001": [
        (
            1,
            "PENDING",
            "helena.tavares",
            None,
            60,
            None,
            "Emissão inicial do balanço de massa.",
            None,
        ),
    ],
    "AK-2200-EST-DWG-0001": [
        (
            1,
            "APPROVED",
            "caio.bertoni",
            "thiago.serpa",
            350,
            344,
            "Emissão inicial do desenho de montagem.",
            None,
        ),
        (
            2,
            "PENDING",
            "caio.bertoni",
            None,
            20,
            None,
            "Troca das ferragens de fixação para liga de titânio.",
            None,
        ),
    ],
    "AK-2200-AER-MEM-0001": [
        (
            1,
            "APPROVED",
            "helena.tavares",
            "beatriz.canuto",
            340,
            330,
            "Emissão inicial do envelope de cargas.",
            None,
        ),
    ],
    "AK-2200-MAT-LDM-0001": [
        (
            1,
            "REJECTED",
            "bruno.kimura",
            "patricia.lemos",
            300,
            296,
            "Emissão inicial da lista de materiais.",
            "Códigos de fixadores divergentes do desenho de montagem.",
        ),
        (
            2,
            "PENDING",
            "bruno.kimura",
            None,
            35,
            None,
            "Correção dos códigos de fixadores apontados na reprovação.",
            None,
        ),
    ],
    "AK-2200-ENS-REV-0001": [
        (
            1,
            "APPROVED",
            "patricia.lemos",
            "thiago.serpa",
            150,
            143,
            "Emissão inicial do relatório de inspeção dimensional.",
            None,
        ),
    ],
    "AK-2200-ENS-REV-0002": [
        (
            1,
            "APPROVED",
            "thiago.serpa",
            "patricia.lemos",
            70,
            64,
            "Emissão inicial da verificação pós tratamento térmico.",
            None,
        ),
    ],
    "AK-3100-EST-DWG-0001": [
        (
            1,
            "APPROVED",
            "leticia.amaral",
            "thiago.serpa",
            310,
            303,
            "Emissão inicial do berço dianteiro.",
            None,
        ),
        (
            2,
            "APPROVED",
            "leticia.amaral",
            "thiago.serpa",
            175,
            168,
            "Ajuste das interfaces dos amortecedores de vibração.",
            None,
        ),
    ],
    "AK-3100-HID-ESP-0001": [
        (
            1,
            "PENDING",
            "diego.vasques",
            None,
            45,
            None,
            "Emissão inicial das rotas hidráulicas.",
            None,
        ),
    ],
    "AK-3100-MAT-NOR-0001": [
        (
            1,
            "APPROVED",
            "joana.prado",
            "patricia.lemos",
            270,
            260,
            "Emissão inicial da norma de torque.",
            "Aprovada para uso na linha de montagem.",
        ),
    ],
    "AK-3100-MAT-NOR-0002": [
        (
            1,
            "APPROVED",
            "joana.prado",
            "thiago.serpa",
            100,
            94,
            "Emissão inicial da norma de rastreabilidade.",
            None,
        ),
    ],
    "AK-3100-ENS-REV-0001": [
        (
            1,
            "APPROVED",
            "beatriz.canuto",
            "patricia.lemos",
            200,
            190,
            "Relatório de ensaio estático até carga limite.",
            "Anexado ao dossiê de certificação.",
        ),
    ],
    "AK-3400-EST-DWG-0001": [
        (
            1,
            "APPROVED",
            "caio.bertoni",
            "thiago.serpa",
            190,
            182,
            "Emissão inicial dos painéis de carenagem.",
            None,
        ),
        (
            2,
            "PENDING",
            "caio.bertoni",
            None,
            8,
            None,
            "Novo ponto de acesso para inspeção do amortecedor.",
            None,
        ),
    ],
    "AK-3400-AER-MEM-0001": [
        (
            1,
            "PENDING",
            "helena.tavares",
            None,
            30,
            None,
            "Emissão inicial da estimativa de arrasto.",
            None,
        ),
    ],
    "AK-3400-FER-PRO-0001": [
        (
            1,
            "APPROVED",
            "bruno.kimura",
            "patricia.lemos",
            170,
            161,
            "Emissão inicial do procedimento de laminação.",
            None,
        ),
    ],
    "AK-4000-FER-DWG-0001": [
        (
            1,
            "APPROVED",
            "bruno.kimura",
            "thiago.serpa",
            420,
            414,
            "Emissão inicial do gabarito de furação.",
            None,
        ),
        (
            2,
            "APPROVED",
            "bruno.kimura",
            "thiago.serpa",
            330,
            322,
            "Substituição das buchas guia por modelo removível.",
            None,
        ),
        (
            3,
            "APPROVED",
            "bruno.kimura",
            "patricia.lemos",
            100,
            92,
            "Nova referência de montagem após revisão do painel.",
            None,
        ),
    ],
    "AK-4000-FER-DWG-0002": [
        (
            1,
            "APPROVED",
            "bruno.kimura",
            "patricia.lemos",
            260,
            252,
            "Emissão inicial do gabarito da empenagem.",
            None,
        ),
    ],
    "AK-4000-FER-GPR-0001": [
        (
            1,
            "APPROVED",
            "bruno.kimura",
            "thiago.serpa",
            200,
            192,
            "Emissão inicial do guia de projeto.",
            None,
        ),
    ],
    "AK-4000-ELE-ESP-0001": [
        (
            1,
            "APPROVED",
            "diego.vasques",
            "thiago.serpa",
            120,
            112,
            "Emissão inicial da especificação elétrica.",
            None,
        ),
    ],
    "AK-4100-ARM-ESP-0001": [
        (
            1,
            "APPROVED",
            "rafael.okamoto",
            "beatriz.canuto",
            160,
            150,
            "Emissão inicial da especificação de integração.",
            None,
        ),
    ],
    "AK-4100-MUN-REV-0001": [
        (
            1,
            "APPROVED",
            "patricia.lemos",
            "beatriz.canuto",
            110,
            100,
            "Emissão inicial do relatório de segurança.",
            "Procedimentos de manuseio considerados adequados.",
        ),
    ],
    "AK-4300-OPT-MEM-0001": [
        (
            1,
            "APPROVED",
            "diego.vasques",
            "thiago.serpa",
            85,
            78,
            "Emissão inicial do memorial de alinhamento.",
            None,
        ),
        (
            2,
            "PENDING",
            "rafael.okamoto",
            None,
            15,
            None,
            "Inclusão da contribuição térmica na cadeia de tolerâncias.",
            None,
        ),
    ],
    "AK-4500-RFE-RTE-0001": [
        (
            1,
            "APPROVED",
            "diego.vasques",
            "patricia.lemos",
            75,
            68,
            "Emissão inicial do relatório de compatibilidade.",
            None,
        ),
    ],
    "AK-4600-EMB-NOR-0001": [
        (
            1,
            "APPROVED",
            "bruno.kimura",
            "patricia.lemos",
            140,
            133,
            "Emissão inicial da norma de embalagem.",
            None,
        ),
    ],
    "AK-5100-COM-ESP-0001": [
        (
            1,
            "APPROVED",
            "renato.fontes",
            "thiago.serpa",
            220,
            212,
            "Emissão inicial da especificação do tanque.",
            None,
        ),
        (
            2,
            "PENDING",
            "renato.fontes",
            None,
            25,
            None,
            "Inclusão de ensaio de estanqueidade após ciclagem de pressão.",
            None,
        ),
    ],
    "AK-5100-COM-MEM-0001": [
        (
            1,
            "APPROVED",
            "renato.fontes",
            "thiago.serpa",
            130,
            121,
            "Emissão inicial do memorial de vazão.",
            None,
        ),
    ],
    "AK-5200-HID-ESP-0001": [
        (
            1,
            "APPROVED",
            "luciana.maeda",
            "patricia.lemos",
            210,
            203,
            "Emissão inicial da especificação do atuador.",
            None,
        ),
        (
            2,
            "APPROVED",
            "luciana.maeda",
            "patricia.lemos",
            90,
            84,
            "Ajuste do curso útil após ensaio de bancada.",
            None,
        ),
    ],
    "AK-5200-HID-DWG-0001": [
        (
            1,
            "APPROVED",
            "luciana.maeda",
            "thiago.serpa",
            95,
            88,
            "Emissão inicial da instalação da central hidráulica.",
            None,
        ),
        (
            2,
            "PENDING",
            "luciana.maeda",
            None,
            6,
            None,
            "Reposicionamento do filtro de retorno para facilitar a manutenção.",
            None,
        ),
    ],
    "AK-5200-HID-GPR-0001": [
        (
            1,
            "APPROVED",
            "luciana.maeda",
            "patricia.lemos",
            50,
            44,
            "Emissão inicial do guia de identificação.",
            None,
        ),
    ],
    "AK-5300-ELE-ESP-0001": [
        (
            1,
            "APPROVED",
            "andre.cardoso",
            "patricia.lemos",
            180,
            172,
            "Emissão inicial da especificação elétrica do módulo.",
            None,
        ),
    ],
    "AK-5400-EST-DWG-0001": [
        (
            1,
            "APPROVED",
            "leticia.amaral",
            "thiago.serpa",
            140,
            132,
            "Emissão inicial do cilindro principal.",
            None,
        ),
    ],
    "AK-2200-EST-MEM-0001": [
        (
            1,
            "APPROVED",
            "leticia.amaral",
            "beatriz.canuto",
            18,
            12,
            "Emissão inicial do memorial da longarina.",
            None,
        ),
    ],
    "AK-4600-EMB-NOR-0002": [
        (
            1,
            "APPROVED",
            "bruno.kimura",
            "patricia.lemos",
            25,
            19,
            "Emissão inicial da norma de embalagem eletrônica.",
            None,
        ),
    ],
    "AK-3400-EST-DWG-0002": [
        (
            1,
            "PENDING",
            "caio.bertoni",
            None,
            5,
            None,
            "Emissão inicial do painel de acesso.",
            None,
        ),
    ],
    "AK-5300-ELE-ESP-0002": [
        (
            1,
            "PENDING",
            "andre.cardoso",
            None,
            3,
            None,
            "Emissão inicial da especificação do barramento.",
            None,
        ),
    ],
    "AK-1500-EST-MEM-0001": [
        (
            1,
            "APPROVED",
            "marina.duarte",
            "beatriz.canuto",
            900,
            890,
            "Emissão inicial. Programa encerrado sem revisão vigente.",
            None,
        ),
    ],
}

# --- files -------------------------------------------------------------------
# Attachments generated per revision, by document type: (filename suffix, extension)
FILES_BY_TYPE = {
    # A drawing is delivered as the plotted PDF plus a raster preview; an
    # inspection report carries the photos that back it up.
    "DWG": [("", "pdf"), ("-preview", "png")],
    "MEM": [("", "pdf")],
    "ESP": [("", "pdf")],
    "NOR": [("", "pdf")],
    "REV": [("", "pdf"), ("-inspecao", "jpeg")],
    "PRO": [("", "docx")],
    "LDM": [("", "pdf")],
    "GPR": [("", "pdf")],
    "MMA": [("", "pdf")],
    "RTE": [("", "pdf")],
}

MIME_TYPES = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "jpeg": "image/jpeg",
    "png": "image/png",
}


# Plausible byte ranges per extension, all within the 100 MB ceiling
SIZE_RANGES = {
    "pdf": (180_000, 7_500_000),
    "doc": (90_000, 1_800_000),
    "docx": (90_000, 1_800_000),
    "jpeg": (400_000, 5_500_000),
    "png": (120_000, 3_200_000),
}

# --- document access ---------------------------------------------------------
# (document, user, status, approver, requested_days_ago, decided_days_ago,
#  justification)
# The approver is always the document's responsible or the manager of one of
# its areas, and a PENDING row never carries an approver. A direct grant has
# no requested_at: nobody asked, the manager just gave access.
DOCUMENT_ACCESS = [
    # SECRET: the responsible plus these users, who include every auditor and
    # revision author that is not the responsible
    (
        "AK-2100-ENS-REV-0001",
        "samuel.rocha",
        "PENDING",
        None,
        6,
        None,
        "Preciso dos resultados de fadiga para preparar o plano de inspeção da linha.",
    ),
    (
        "AK-2100-ENS-REV-0001",
        "diego.vasques",
        "APPROVED",
        "thiago.serpa",
        40,
        38,
        "Avaliação do impacto dos resultados nas rotas de sistemas.",
    ),
    ("AK-2100-ENS-REV-0001", "beatriz.canuto", "APPROVED", "thiago.serpa", None, 235, None),
    ("AK-2200-AER-MEM-0001", "bruno.kimura", "APPROVED", "marina.duarte", None, 25, None),
    ("AK-2200-AER-MEM-0001", "beatriz.canuto", "APPROVED", "helena.tavares", None, 338, None),
    (
        "AK-3100-ENS-REV-0001",
        "caio.bertoni",
        "PENDING",
        None,
        3,
        None,
        "Referência para o dimensionamento do berço na próxima revisão.",
    ),
    (
        "AK-3100-ENS-REV-0001",
        "samuel.rocha",
        "REJECTED",
        "beatriz.canuto",
        70,
        66,
        "Curiosidade técnica sobre o ensaio.",
    ),
    ("AK-3100-ENS-REV-0001", "patricia.lemos", "APPROVED", "beatriz.canuto", None, 198, None),
    ("AK-3100-ENS-REV-0001", "leticia.amaral", "APPROVED", "beatriz.canuto", None, 195, None),
    ("AK-4100-ARM-ESP-0001", "beatriz.canuto", "APPROVED", "rafael.okamoto", None, 158, None),
    ("AK-4100-ARM-ESP-0001", "diego.vasques", "APPROVED", "rafael.okamoto", None, 140, None),
    ("AK-4100-MUN-REV-0001", "patricia.lemos", "APPROVED", "thiago.serpa", None, 108, None),
    ("AK-4100-MUN-REV-0001", "beatriz.canuto", "APPROVED", "thiago.serpa", None, 108, None),
    (
        "AK-4100-MUN-REV-0001",
        "samuel.rocha",
        "PENDING",
        None,
        2,
        None,
        "Necessário conhecer os requisitos de segurança para embalar as munições inertes.",
    ),
    ("AK-4300-OPT-MEM-0001", "thiago.serpa", "APPROVED", "diego.vasques", None, 84, None),
    ("AK-4300-OPT-MEM-0001", "rafael.okamoto", "APPROVED", "diego.vasques", None, 80, None),
    # CONFIDENTIAL: users outside the document's areas asking for access
    ("AK-2100-EST-MEM-0001", "samuel.rocha", "APPROVED", "leticia.amaral", None, 55, None),
    (
        "AK-3100-HID-ESP-0001",
        "helena.tavares",
        "PENDING",
        None,
        9,
        None,
        "Verificar interferência entre rotas hidráulicas e o carenamento.",
    ),
    (
        "AK-3400-FER-PRO-0001",
        "diego.vasques",
        "APPROVED",
        "bruno.kimura",
        100,
        96,
        "Alinhar o ferramental de laminação com a instalação elétrica da autoclave.",
    ),
    (
        "AK-5100-COM-MEM-0001",
        "helena.tavares",
        "PENDING",
        None,
        4,
        None,
        "Verificar o impacto do arrasto dos tanques na estimativa de desempenho.",
    ),
    (
        "AK-5200-HID-DWG-0001",
        "samuel.rocha",
        "REJECTED",
        "luciana.maeda",
        30,
        28,
        "Consulta sem relação com as atividades da manufatura.",
    ),
]

# -- Legal documents ---------------------------------------------------------

LEGAL_DOCUMENT_SLUG = "termo-tratamento-dados"
LEGAL_DOCUMENT_TITLE = "Termo de Adesão ao Tratamento de Dados Pessoais – Pragma Co"
LEGAL_VERSION = 1
LEGAL_VERSION_AUTHOR = "marina.duarte"
LEGAL_VERSION_NOTES = "Versão inicial."
LEGAL_VERSION_SUMMARY = (
    "Declaração do Titular: Declaro que li e compreendi integralmente o presente Termo, "
    "tendo-me sido esclarecidos os meus direitos nos termos da LGPD. Concordo com o "
    "conteúdo deste Termo e concordo com o tratamento dos meus dados pessoais conforme "
    "as finalidades descritas neste Termo."
)

# (code, title, is_required, body). Position is the index in the list.
LEGAL_CLAUSES = [
    (
        "partes",
        "Artigo 1º – Partes",
        True,
        "Titular dos Dados: Todo funcionário da Pragma Co que acessa este sistema "
        '(doravante denominado "Titular").\n\n'
        "Controlador: Pragma Co, com endereço em [endereço da empresa].\n\n"
        "Encarregado de Proteção de Dados (DPO): Augusto de Moraes Piatto. "
        "E-mail de contato: dpo@pragmaco.com",
    ),
    (
        "objeto",
        "Artigo 2º – Objeto do Termo",
        True,
        "Este Termo tem por objeto esclarecer ao Titular como seus dados pessoais são "
        "coletados, utilizados, armazenados e compartilhados no sistema interno da "
        "Pragma Co, bem como obter seu consentimento para o tratamento de dados "
        "pessoais. Este Termo observa a Lei Geral de Proteção de Dados Pessoais do "
        'Brasil (Lei nº 13.709/2018, "LGPD").',
    ),
    (
        "dados-coletados",
        "Artigo 3º – Âmbito dos Dados Pessoais Coletados",
        True,
        "A Pragma Co coletará e tratará os seguintes dados pessoais do Titular no "
        "sistema interno:\n\n"
        "1. Nome;\n2. E-mail corporativo;\n3. Número de matrícula;\n4. Departamento;\n5. Cargo.",
    ),
    (
        "registros-de-acesso",
        "Artigo 4º – Registros de Acesso",
        True,
        "Para garantir a segurança da informação e a conformidade das operações, o "
        "sistema registrará automaticamente as atividades de login e acesso do Titular, "
        "incluindo, mas não se limitando a: endereço IP, horário de acesso, dispositivo "
        "utilizado e operações realizadas no sistema. Tais registros destinam-se "
        "exclusivamente a auditoria de segurança e rastreabilidade de incidentes.",
    ),
    (
        "finalidade",
        "Artigo 5º – Finalidade do Tratamento",
        True,
        "Os dados pessoais coletados serão utilizados para as seguintes finalidades "
        "específicas:\n\n"
        "1. Controle de identidade e verificação de acesso ao sistema;\n"
        "2. Controle de permissões de acesso a documentos técnicos;\n"
        "3. Auditoria de segurança e rastreabilidade de operações;\n"
        "4. Cumprimento de obrigações contratuais ou acordos de confidencialidade "
        "decorrentes do contrato de trabalho.",
    ),
    (
        "base-legal",
        "Artigo 6º – Base Legal do Tratamento",
        True,
        "O tratamento de dados pessoais previsto neste Termo fundamenta-se no disposto "
        'no artigo 7º, inciso V da LGPD, ou seja: "quando necessário para a execução '
        "de contrato ou de procedimentos preliminares relacionados a contrato do qual "
        'seja parte o titular, a pedido do titular dos dados", ou seja, o tratamento '
        "de dados é necessário para a execução do contrato de trabalho entre o Titular "
        "e a Pragma Co.",
    ),
    (
        "transferencia-internacional",
        "Artigo 7º – Transferência Internacional de Dados",
        False,
        "Considerando que a Pragma Co possui operações comerciais globais, os dados "
        "pessoais do Titular podem ser transferidos para fora do território brasileiro "
        "para as finalidades de gestão e administração de recursos humanos.\n\n"
        "A Pragma Co compromete-se a adotar Cláusulas Contratuais Padrão "
        "(Cláusulas-Padrão Contratuais) aprovadas pela Autoridade Nacional de Proteção "
        "de Dados (ANPD) do Brasil como mecanismo de garantia para transferência "
        "internacional de dados, assegurando que os dados pessoais recebam, no exterior, "
        "nível de proteção equivalente ao da LGPD.",
    ),
    (
        "retencao",
        "Artigo 8º – Período de Retenção de Dados",
        True,
        "Os dados pessoais do Titular serão armazenados por um período de máximo 2 "
        "(dois) anos, contados a partir da data de encerramento da relação laboral ou "
        "da data de revogação deste Termo pelo Titular.\n\n"
        "Após o término do período acima, a Pragma Co eliminará ou anonimizará os dados "
        "pessoais, salvo quando a lei exigir prazo de retenção mais longo.",
    ),
    (
        "direitos-do-titular",
        "Artigo 9º – Direitos do Titular",
        True,
        "Nos termos do artigo 18º da LGPD, o Titular tem os seguintes direitos:\n\n"
        "1. Direito de confirmação e acesso: Confirmar se a Pragma Co trata seus dados "
        "pessoais e acessar os dados;\n"
        "2. Direito de correção: Solicitar a correção de dados pessoais incompletos, "
        "inexatos ou desatualizados;\n"
        "3. Direito de anonimização, bloqueio ou eliminação: Solicitar a anonimização, "
        "bloqueio ou eliminação de dados desnecessários, excessivos ou tratados em "
        "desconformidade com a LGPD;\n"
        "4. Direito à portabilidade: Solicitar a portabilidade dos dados a outro "
        "fornecedor de serviço ou produto;\n"
        "5. Direito à eliminação: Solicitar a eliminação dos dados pessoais tratados "
        "com base no consentimento do Titular;\n"
        "6. Direito à informação: Obter informações sobre entidades públicas e privadas "
        "com as quais a Pragma Co compartilhou seus dados.",
    ),
    (
        "exercicio-dos-direitos",
        "Artigo 10º – Forma de Exercício dos Direitos",
        True,
        "O Titular pode exercer os direitos previstos no artigo 9º entrando em contato "
        "com o Encarregado de Proteção de Dados (DPO) através do e-mail: "
        "dpo@pragmaco.com.",
    ),
    (
        "medidas-de-seguranca",
        "Artigo 11º – Medidas de Segurança",
        True,
        "A Pragma Co adotará as seguintes medidas técnicas e organizacionais para "
        "proteger os dados pessoais:\n\n"
        "1. Controle de acesso baseado em funções (RBAC);\n"
        "2. Criptografia de dados;\n"
        "3. Registro de logs de acesso e auditoria;\n"
        "4. Treinamento periódico de conscientização sobre proteção de dados para "
        "funcionários.",
    ),
    (
        "limitacao-de-acesso",
        "Artigo 12º – Limitação de Acesso a Documentos",
        True,
        "O Titular reconhece e concorda que os documentos acessados através do sistema "
        "podem conter informações técnicas confidenciais. Os documentos são "
        "configurados com restrições de visualização apenas, sendo proibido baixar, "
        "copiar ou de qualquer forma exportar documentos para fora do sistema. O "
        "Titular cumprirá as obrigações de confidencialidade previstas no contrato de "
        "trabalho.",
    ),
    (
        "revogacao",
        "Artigo 13º – Revogação",
        True,
        "O Titular pode revogar este Termo a qualquer momento. No entanto, o Titular "
        "reconhece que a revogação pode impedir seu acesso ao sistema, por meio do "
        "qual a Pragma Co cumpre as obrigações de contrato de trabalho.",
    ),
    (
        "vigencia",
        "Artigo 14º – Vigência",
        True,
        "Este Termo entra em vigor na data de sua assinatura pelo Titular e permanece "
        "válido enquanto durar a relação laboral entre o Titular e a Pragma Co, ou "
        "conforme necessário para cumprir obrigações legais.",
    ),
    (
        "legislacao-e-foro",
        "Artigo 15º – Legislação Aplicável e Foro",
        True,
        "Este Termo rege-se pelas leis da República Federativa do Brasil. Eventuais "
        "controvérsias serão resolvidas no foro competente da comarca de "
        "[localização da empresa].",
    ),
]

ACCESS_GROUPS = [
    (
        "Engenharia Estrutural — sigiloso",
        "AREA",
        "EST",
        None,
        "CONFIDENTIAL",
        "marina.duarte",
        ["samuel.rocha", "helena.tavares"],
        "Engenheiros de outras áreas que acompanham a documentação sigilosa de estruturas.",
    ),
    (
        "Fuselagem central — restrito",
        "PROJECT",
        None,
        "AK-2100",
        "SECRET",
        "marina.duarte",
        ["caio.bertoni", "thiago.serpa"],
        "Usuários autorizados a consultar os documentos restritos do programa AK-2100.",
    ),
    (
        "Qualidade e Inspeção — sigiloso",
        "AREA",
        "QUA",
        None,
        "CONFIDENTIAL",
        "thiago.serpa",
        ["bruno.kimura"],
        "Apoio da manufatura aos documentos sigilosos de qualidade.",
    ),
]
