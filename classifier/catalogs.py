from __future__ import annotations

from typing import Dict, List

BOT_BRAND_NAME = "OfferFlow"
BOT_DISPLAY_NAME = "OfferFlow Assistente"

HUB_CHANNEL_SPEC: Dict[str, str] = {
    "key": "hub",
    "title": "⚡ Comunidade OfferFlow • Ofertas ML",
    "short_name": "Comunidade OfferFlow",
    "emoji": "⚡",
    "description": (
        "⚡ Comunidade Oficial OfferFlow — Curadoria 100% Mercado Livre com produtos novos/recondicionados, "
        "vendedores reputação Verde/Amarela e acesso rápido aos nossos 8 canais de categorias."
    ),
    "welcome_text": (
        "⚡ <b>BEM-VINDO À COMUNIDADE OFFERFLOW</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Aqui você encontra os <b>melhores achados, cupons e quedas reais de preço</b> selecionados "
        "com curadoria rigorosa no <b>Mercado Livre</b>:\n\n"
        "✅ <b>Apenas produtos Novos ou Recondicionados</b>\n"
        "🏅 <b>Apenas vendedores com reputação Verde ou Amarela</b>\n"
        "⚡ <b>Verificação automática de preço e estoque antes da postagem</b>\n\n"
        "👇 <b>Escolha abaixo os canais das categorias que você mais gosta (ou adicione a Pasta Completa):</b>"
    ),
}

OFFICIAL_TOPICS: Dict[str, str] = {
    "ofertas_bugs": "🔥 Ofertas Relâmpago & Bugs",
    "tech_celulares": "💻 Tech, Informática & Celulares",
    "games_geek": "🎮 Games, Brinquedos & Livros",
    "casa_eletro": "🏠 Casa, Eletro & Cozinha",
    "ferramentas_construcao": "🛠️ Ferramentas & Construção",
    "moda_relogios": "👟 Moda, Calçados & Relógios",
    "beleza_esportes": "💄 Beleza, Saúde & Esportes",
    "pet_bebes_papelaria": "🐾 Pet, Bebês & Papelaria",
}

TOPIC_EMOJIS: Dict[str, str] = {
    "ofertas_bugs": "🔥",
    "tech_celulares": "💻",
    "games_geek": "🎮",
    "casa_eletro": "🏠",
    "ferramentas_construcao": "🛠️",
    "moda_relogios": "👟",
    "beleza_esportes": "💄",
    "pet_bebes_papelaria": "🐾",
}

CHANNEL_CATALOG: Dict[str, Dict[str, str]] = {
    "hub": HUB_CHANNEL_SPEC,
    "ofertas_bugs": {
        "key": "ofertas_bugs",
        "title": "OfferFlow • 🔥 Ofertas Relâmpago & Bugs",
        "short_name": "Ofertas Relâmpago & Bugs",
        "emoji": "🔥",
        "description": (
            "🔥 Super descontos, Ofertas Relâmpago, cupons imperdíveis e quedas históricas "
            "no Mercado Livre. Parte da Comunidade OfferFlow."
        ),
        "welcome_text": (
            "🔥 <b>OfferFlow • Ofertas Relâmpago & Bugs</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Os maiores descontos, cupons relâmpago e recordes de preço do Mercado Livre em tempo real!\n"
            "🔔 Ative as notificações para não perder nenhuma queda brusca."
        ),
    },
    "tech_celulares": {
        "key": "tech_celulares",
        "title": "OfferFlow • 💻 Tech, Informática & Celulares",
        "short_name": "Tech, Informática & Celulares",
        "emoji": "💻",
        "description": (
            "💻 Smartphones, notebooks, hardware PC, monitores, fones, áudio, vídeo e câmeras "
            "no Mercado Livre. Parte da Comunidade OfferFlow."
        ),
        "welcome_text": (
            "💻 <b>OfferFlow • Tech, Informática & Celulares</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Promoções verificadas em Celulares, Informática, Eletrônicos, Áudio, Vídeo e Câmeras no Mercado Livre."
        ),
    },
    "games_geek": {
        "key": "games_geek",
        "title": "OfferFlow • 🎮 Games, Brinquedos & Livros",
        "short_name": "Games, Brinquedos & Livros",
        "emoji": "🎮",
        "description": (
            "🎮 Consoles, jogos físicos, controles, LEGO, board games, brinquedos e livros/HQs novos "
            "no Mercado Livre. Parte da Comunidade OfferFlow."
        ),
        "welcome_text": (
            "🎮 <b>OfferFlow • Games, Brinquedos & Livros</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Ofertas em Videogames, Jogos, Brinquedos e Livros/Quadrinhos novos no Mercado Livre."
        ),
    },
    "casa_eletro": {
        "key": "casa_eletro",
        "title": "OfferFlow • 🏠 Casa, Eletro & Cozinha",
        "short_name": "Casa, Eletro & Cozinha",
        "emoji": "🏠",
        "description": (
            "🏠 Airfryers, cafeteiras, geladeiras, aspiradores, móveis, decoração e utilidades "
            "no Mercado Livre. Parte da Comunidade OfferFlow."
        ),
        "welcome_text": (
            "🏠 <b>OfferFlow • Casa, Eletro & Cozinha</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Os melhores preços em Eletrodomésticos, Casa, Móveis e Decoração no Mercado Livre."
        ),
    },
    "ferramentas_construcao": {
        "key": "ferramentas_construcao",
        "title": "OfferFlow • 🛠️ Ferramentas & Construção",
        "short_name": "Ferramentas & Construção",
        "emoji": "🛠️",
        "description": (
            "🛠️ Furadeiras, parafusadeiras, kits de ferramentas, iluminação e materiais de construção "
            "no Mercado Livre. Parte da Comunidade OfferFlow."
        ),
        "welcome_text": (
            "🛠️ <b>OfferFlow • Ferramentas & Construção</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Ofertas selecionadas em Ferramentas elétricas, manuais e itens de Construção no Mercado Livre."
        ),
    },
    "moda_relogios": {
        "key": "moda_relogios",
        "title": "OfferFlow • 👟 Moda, Calçados & Relógios",
        "short_name": "Moda, Calçados & Relógios",
        "emoji": "👟",
        "description": (
            "👟 Tênis, calçados, roupas, bolsas, mochilas, óculos, joias e relógios originais "
            "no Mercado Livre. Parte da Comunidade OfferFlow."
        ),
        "welcome_text": (
            "👟 <b>OfferFlow • Moda, Calçados & Relógios</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Descontos verificados em Calçados, Roupas, Bolsas, Joias e Relógios no Mercado Livre."
        ),
    },
    "beleza_esportes": {
        "key": "beleza_esportes",
        "title": "OfferFlow • 💄 Beleza, Saúde & Esportes",
        "short_name": "Beleza, Saúde & Esportes",
        "emoji": "💄",
        "description": (
            "💄 Perfumes, skincare, cuidados pessoais, cabelo, academia, bikes e esportes & fitness "
            "no Mercado Livre. Parte da Comunidade OfferFlow."
        ),
        "welcome_text": (
            "💄 <b>OfferFlow • Beleza, Saúde & Esportes</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Curadoria em Beleza, Perfumes, Cuidado Pessoal, Bem-Estar e Esportes & Fitness no Mercado Livre."
        ),
    },
    "pet_bebes_papelaria": {
        "key": "pet_bebes_papelaria",
        "title": "OfferFlow • 🐾 Pet, Bebês & Papelaria",
        "short_name": "Pet, Bebês & Papelaria",
        "emoji": "🐾",
        "description": (
            "🐾 Acessórios e rações Pet Shop, enxoval e carrinhos para Bebês, papelaria, arte, festas "
            "e instrumentos musicais no Mercado Livre. Parte da Comunidade OfferFlow."
        ),
        "welcome_text": (
            "🐾 <b>OfferFlow • Pet, Bebês & Papelaria</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Ofertas selecionadas em Pet Shop (acessórios e rações), Bebês, Papelaria, Festas e Instrumentos Musicais."
        ),
    },
}

ML_CATEGORY_HUNTER_ROUTES: List[Dict[str, str]] = [
    {"category_key": "tech_celulares", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB1648"},
    {"category_key": "tech_celulares", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB1051"},
    {"category_key": "tech_celulares", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB1000"},
    {"category_key": "tech_celulares", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB1039"},
    {"category_key": "games_geek", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB1144"},
    {"category_key": "games_geek", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB1132"},
    {"category_key": "games_geek", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB1196"},
    {"category_key": "casa_eletro", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB5726"},
    {"category_key": "casa_eletro", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB1574"},
    {"category_key": "ferramentas_construcao", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB263532"},
    {"category_key": "ferramentas_construcao", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB1500"},
    {"category_key": "moda_relogios", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB1430"},
    {"category_key": "moda_relogios", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB3937"},
    {"category_key": "beleza_esportes", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB1246"},
    {"category_key": "beleza_esportes", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB1276"},
    {"category_key": "pet_bebes_papelaria", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB1071"},
    {"category_key": "pet_bebes_papelaria", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB1384"},
    {"category_key": "pet_bebes_papelaria", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB1368"},
    {"category_key": "pet_bebes_papelaria", "url": "https://www.mercadolivre.com.br/mais-vendidos/MLB1182"},
]

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "tech_celulares": [
        "smartphone", "celular", "iphone", "galaxy", "motorola", "xiaomi", "redmi", "poco",
        "realme", "notebook", "macbook", "laptop", "ultrabook", "tablet", "ipad", "kindle",
        "monitor", "placa de video", "rtx", "gtx", "radeon", "processador", "ryzen", "intel core",
        "placa mae", "memoria ram", "ddr4", "ddr5", "ssd", "nvme", "hd externo", "pendrive",
        "fonte atx", "gabinete", "water cooler", "air cooler", "teclado mecanico", "mouse gamer",
        "mouse sem fio", "headset", "fone bluetooth", "fone de ouvido", "earbuds", "airpods",
        "caixa de som", "jbl", "soundbar", "microfone", "webcam", "roteador", "mesh", "repetidor",
        "impressora", "multifuncional", "smart tv", "tv 4k", "oled", "qled", "projetor", "fire tv",
        "chromecast", "apple tv", "echo dot", "alexa", "smartwatch", "apple watch", "mi band",
        "galaxy watch", "power bank", "carregador", "cabo usb", "hub usb", "camera", "gopro",
        "instax", "lente fotografica", "tripe", "ring light", "drone", "nobreak", "estabilizador",
        "fechadura digital", "camera de seguranca", "interruptor inteligente", "tomada inteligente",
    ],
    "games_geek": [
        "playstation", "ps5", "ps4", "xbox", "nintendo", "switch", "steam deck", "rog ally",
        "controle sem fio", "dualsense", "joy-con", "volante gamer", "cadeira gamer", "mesa gamer",
        "jogo ps5", "jogo ps4", "jogo switch", "jogo xbox", "videogame", "console",
        "brinquedo", "lego", "hot wheels", "barbie", "nerf", "playmobil", "boneca", "boneco",
        "action figure", "funko", "jogo de tabuleiro", "board game", "quebra cabeca", "uno",
        "war", "banco imobiliario", "detetive", "pelucia", "patinete infantil", "bicicleta infantil",
        "livro", "box livros", "hq", "quadrinho", "manga", "gibis", "revista", "kindle unlimited",
    ],
    "casa_eletro": [
        "airfryer", "air fryer", "fritadeira", "geladeira", "refrigerador", "freezer", "frigobar",
        "fogao", "cooktop", "forno eletrico", "micro-ondas", "microondas", "lava-loucas",
        "lava e seca", "maquina de lavar", "tanquinho", "secadora", "ar-condicionado",
        "ar condicionado", "climatizador", "ventilador", "circulador", "umidificador", "purificador",
        "bebedouro", "cafeteira", "nespresso", "dolce gusto", "moedor de cafe", "chaleira eletrica",
        "liquidificador", "batedeira", "mixer", "processador de alimentos", "sanduicheira", "grill",
        "torradeira", "panela eletrica", "panela de pressao", "jogo de panelas", "frigideira",
        "tramontina", "faqueiro", "aparelho de jantar", "copo termico", "stanley", "garrafa termica",
        "pote hermetico", "aspirador", "robo aspirador", "wap", "passadeira", "ferro de passar",
        "sofa", "poltrona", "cadeira de escritorio", "cadeira ergonomica", "escrivaninha",
        "mesa de jantar", "guarda-roupa", "colchao", "travesseiro", "jogo de cama", "lencol",
        "edredom", "cobertor", "toalha de banho", "cortina", "tapete", "luminaria", "abajur",
        "espelho", "organizador", "varal", "mop", "lixeira", "churrasqueira", "adega climatizada",
        "cervejeira", "difusor de ambiente", "aromatizador", "coala",
    ],
    "ferramentas_construcao": [
        "furadeira", "parafusadeira", "martelete", "esmerilhadeira", "serra circular",
        "serra tico-tico", "serra marmore", "lixadeira", "plaina", "tupia", "soprador termico",
        "lavadora de alta pressao", "compressor de ar", "maquina de solda", "inversora",
        "jogo de ferramentas", "maleta de ferramentas", "chave de fenda", "chave catraca",
        "chave inglesa", "alicate", "martelo", "trena", "trena laser", "nivel a laser",
        "multimetro", "alicate amperimetro", "ferro de solda", "estacao de solda", "escada",
        "bosch", "makita", "dewalt", "stanley ferramentas", "vonder", "black+decker", "wap ferramentas",
        "torneira", "chuveiro", "ducha", "lorenzetti", "misturador", "cuba", "ralo",
        "fechadura", "cadeado", "tinta acrilica", "verniz", "silicone", "vedante", "lampada led",
        "refletor led", "painel led", "disjuntor", "cabo flexivel", "extensao eletrica",
        "filtro de linha", "iclamper", "tomada", "porcelanato", "rejunte", "argamassa",
    ],
    "moda_relogios": [
        "tenis", "sapato", "sapatenis", "bota", "coturno", "sandalia", "chinelo", "havaianas",
        "crocs", "papete", "mocassim", "chuteira", "nike", "adidas", "puma", "asics", "mizuno",
        "olympikus", "fila", "new balance", "vans", "converse", "all star", "under armour",
        "camiseta", "camisa", "polo", "blusa", "moletom", "jaqueta", "casaco", "calca jeans",
        "bermuda", "shorts", "vestido", "saia", "pijama", "cueca", "calcinha", "sutia", "meia",
        "hering", "lacoste", "reserva", "levi's", "levis", "calvin klein", "tommy hilfiger",
        "bolsa", "mochila", "mala de viagem", "carteira", "cinto", "bone", "oculos de sol",
        "ray-ban", "oakley", "relogio", "casio", "g-shock", "seiko", "orient", "technos",
        "mormaii", "fossil", "invicta", "joia", "alianca", "anel", "brinco", "colar", "pulseira",
    ],
    "beleza_esportes": [
        "perfume", "eau de parfum", "eau de toilette", "colonia", "body splash", "desodorante",
        "shampoo", "condicionador", "mascara capilar", "oleo capilar", "leave-in", "acidificante",
        "protetor termico", "escova secadora", "secador de cabelo", "chapinha", "prancha",
        "modelador", "babyliss", "maquina de cortar cabelo", "barbeador", "aparador de pelos",
        "prestobarba", "gillette", "hidratante", "creme facial", "serum", "vitamina c facial",
        "retinol", "acido hialuronico", "niacinamida", "protetor solar", "gel de limpeza",
        "sabonete facial", "sabonete liquido", "esfoliante", "maquiagem", "batom", "base facial",
        "rimel", "mascara de cilios", "corretivo", "paleta de sombras", "blush", "demaquilante",
        "cerave", "la roche", "bioderma", "eucerin", "neutrogena", "nivea", "dove", "loreal",
        "wella", "kerastase", "truss", "lola", "pantene", "principia", "sallve", "bepantol",
        "escova dental eletrica", "escova de dente eletrica", "escova eletrica", "sonicpro", "oral-b",
        "irrigador oral", "balanca digital", "massageador",
        "bicicleta", "bike", "esteira", "bicicleta ergometrica", "eliptico", "halter", "anilha",
        "kettlebell", "barra fixa", "corda de pular", "elastico de treino", "faixa elastica",
        "tapete de yoga", "colchonete", "bola de futebol", "bola de basquete", "bola de volei",
        "raquete", "beach tennis", "tenis de mesa", "luva de boxe", "saco de pancada",
        "barraca de camping", "colchao inflavel", "saco de dormir", "lanterna tatica",
        "garrafa esportiva", "coqueteleira", "patins", "skate", "oculos de natacao",
    ],
    "pet_bebes_papelaria": [
        "racao", "petisco", "sache", "whiskas", "pedigree", "golden", "premier", "royal canin",
        "granplus", "formula natural", "areia higienica", "tapete higienico", "arranhador",
        "cama pet", "caminha cachorro", "caminha gato", "coleira", "guia peitoral", "caixa de transporte",
        "comedouro", "bebedouro fonte pet", "antipulgas", "simparic", "bravecto", "nexgard",
        "brinquedo pet", "shampoo pet",
        "carrinho de bebe", "bebe conforto", "cadeirinha para auto", "berco portatil", "cercadinho",
        "banheira bebe", "trocador", "baba eletronica", "bomba tira leite", "mamadeira", "chupeta",
        "copo de transicao", "esterilizador", "fralda infantil", "pampers", "huggies", "lenco umedecido",
        "canguru bebe", "cadeira de alimentacao", "andador", "tapete de atividades", "enxoval bebe",
        "caderno", "fichario", "agenda", "planner", "caneta", "marca texto", "stabilo", "faber-castell",
        "lapis de cor", "giz de cera", "tinta guache", "tinta acrilica tela", "pincel artistico",
        "tela de pintura", "estojo", "mochila escolar", "lancheira", "calculadora cientifica",
        "papel sulfite", "papel fotografico", "plastificadora", "guilhotina papel", "maquina de costura",
        "linha de croche", "la de trico", "armarinho", "tecido", "balao festa", "decoracao festa",
        "lembrancinha", "vela aniversario", "fantasia",
        "violao", "guitarra", "baixo", "teclado musical", "piano digital", "bateria eletronica",
        "ukulele", "cavaquinho", "cajon", "microfone condensador", "interface de audio", "amplificador",
        "pedal de guitarra", "encordoamento", "suporte violao", "flauta", "gaita", "saxofone",
    ],
}

ML_BLOCKED_FOOD_BEVERAGE: List[str] = [
    "chocolate", "bombom", "barra de chocolate", "trufa", "alfajor", "biscoito", "bolacha",
    "wafer", "salgadinho", "chips", "pringles", "doritos", "takis", "cheetos", "bala", "chiclete",
    "goma de mascar", "marshmallow", "pirulito", "pacoca", "pe de moleque", "goiabada",
    "doce de leite", "geleia", "mel puro", "nutella", "creme de avela", "pasta de amendoim",
    "milka", "lindt", "lindor", "toblerone", "ferrero", "raffaello", "kinder", "havanna",
    "garoto", "lacta", "nestle especialidades", "sonho de valsa", "serenata de amor",
    "ouro branco", "bis xtra", "prestigio", "chokito", "diamante negro", "laka", "baton",
    "passatempo", "trakinas", "negresco", "oreo", "biscoff", "lotus", "pocky", "mochi",
    "arroz", "feijao", "macarrao", "espaguete", "spaghetti", "lamen", "miojo", "ramen",
    "samyang", "buldak", "nongshim", "barilla", "de cecco", "molho de tomate", "passata",
    "ketchup", "mostarda", "maionese", "shoyu", "sriracha", "tabasco", "azeite", "oleo de soja",
    "vinagre", "aceto balsamico", "acucar", "sal grosso", "tempero", "farinha", "aveia",
    "granola", "cereal matinal", "pao de forma", "panettone", "chocottone", "torrada",
    "leite condensado", "creme de leite", "leite em po", "leite integral", "leite uht",
    "queijo", "manteiga", "margarina", "requeijao", "iogurte", "sardinha", "atum em lata",
    "carne", "picanha", "bacon", "linguica", "salsicha", "presunto", "castanha", "amendoim",
    "pistache", "nozes", "cesta basica", "achocolatado", "nescau", "toddy", "toddynho",
    "cafe em graos", "cafe moido", "cafe soluvel", "capsula de cafe", "capsulas de cafe",
    "cafe pilao", "cafe melitta", "cafe 3 coracoes", "cafe illy", "cafe lavazza", "cha mate",
    "refrigerante", "coca-cola", "coca cola", "guarana", "pepsi", "dr pepper", "energetico",
    "red bull", "monster energy", "suco de", "agua mineral", "agua com gas", "agua de coco",
    "cerveja", "chopp", "heineken", "stella artois", "corona", "budweiser", "spaten",
    "vinho", "espumante", "champagne", "champanhe", "veuve clicquot", "moet", "freixenet",
    "whisky", "whiskey", "johnnie walker", "chivas", "old parr", "jack daniel", "ballantine",
    "buchanan", "macallan", "jameson", "vodka", "absolut", "grey goose", "smirnoff", "ciroc",
    "gin ", "tanqueray", "beefeater", "bombay sapphire", "hendrick", "seagers",
    "rum ", "tequila", "cachaca", "licor", "aperol", "campari", "baileys", "amarula",
    "jagermeister", "xarope dilute", "xarope monin", "soda italiana",
    "formula infantil", "aptamil", "nan comfor", "nan supreme", "nestogeno", "enfamil",
    "papinha", "mucilon", "farinha lactea", "composto lacteo", "milnutri", "ninho fases",
    "whey protein", "creatina", "hipercalorico", "pre-treino", "pre treino", "bcaa",
    "glutamina", "albumina", "barra de proteina", "colageno em po", "energetico em po",
]

NON_FOOD_SAFE_EQUIPMENT: List[str] = [
    "cafeteira", "moedor de cafe", "prensa francesa", "garrafa termica", "copo termico",
    "caneca", "xicara", "taca de vinho", "taca de gin", "taca de champagne", "adega",
    "cervejeira", "chopeira", "abridor de vinho", "saca rolha", "balde de gelo",
    "coqueteleira", "kit caipirinha", "kit churrasco", "panela", "frigideira", "forma de bolo",
    "pote hermetico", "porta tempero", "galheteiro", "saleiro", "acucareiro", "manteigueira",
    "queijeira", "pipoqueira", "sorveteira", "iogurteira", "sanduicheira", "chaleira",
    "liquidificador", "batedeira", "airfryer", "air fryer", "fritadeira", "geladeira",
    "micro-ondas", "microondas", "fogao", "forno", "bebedouro", "purificador",
    "racao", "petisco", "sache", "whiskas", "pedigree", "golden", "premier", "royal canin",
    "perfume", "hidratante", "shampoo", "condicionador", "sabonete", "batom", "creme",
    "difusor", "aromatizador", "vela aromatica", "camiseta", "tenis", "cor chocolate",
    "cor vinho", "cor cafe", "cor mel", "cor champanhe", "cor laranja",
]

ML_BLOCKED_MEDICAL_PHARMA: List[str] = [
    "medicamento", "remedio", "farmaceutico", "antibiotico", "anti-inflamatorio",
    "analgesico", "dipirona", "paracetamol", "ibuprofeno", "omeprazol", "amoxicilina",
    "losartana", "metformina", "rivotril", "clonazepam", "antidepressivo", "ansiolitico",
    "colirio", "pomada medicinal", "xarope expectorante", "antigripal", "antialergico",
    "suplemento vitaminico", "multivitaminico", "polivitaminico", "melatonina", "omega 3",
    "magnesio dimalato", "vitamina d3", "vitamina b12", "ferro quelato", "probiotico",
    "seringa", "agulha descartavel", "cateter", "sonda uretral", "sonda nasogastrica",
    "para maca", "lencol de papel descartavel",
    "estetoscopio", "esfigmomanometro", "aparelho de pressao", "oximetro", "glicosimetro",
    "tira de glicemia", "lanceta", "nebulizador", "inalador", "termometro clinico",
    "termometro digital infravermelho", "otoscopio", "luva cirurgica", "luva de procedimento",
    "mascara cirurgica", "mascara n95", "gaze esteril", "atadura", "esparadrapo",
    "curativo esteril", "micropore", "alcool 70", "alcool swab", "clorexidina",
    "fralda geriatrica", "fralda adulto", "incontinencia urinaria", "ostomia", "colostomia",
    "coloplast", "lencol hospitalar", "lencol de maca", "lencol descartavel", "hospitalar",
    "comadre hospitalar", "papagaio hospitalar", "fixador de dentadura", "protese dentaria",
    "cadeira de rodas", "muleta", "andador ortopedico", "bota imobilizadora", "tipoia",
    "meia de compressao medicinal", "teste de gravidez", "teste covid", "preservativo",
]

ML_BLOCKED_USED_TERMS: List[str] = [
    "usado", "usada", "usados", "usadas", "seminovo", "seminova", "semi novo", "semi nova",
    "segunda mao", "2a mao", "de vitrine usado", "com marcas de uso", "no estado",
    "para retirada de pecas", "com defeito", "sebo ", "livro usado",
]

ML_BLOCKED_LIVE_ANIMALS: List[str] = [
    "filhote de", "filhotes de", "venda de cachorro", "venda de gato", "cao de raca",
    "canario vivo", "calopsita viva", "papagaio vivo", "peixe ornamental vivo",
    "betta vivo", "aquario com peixes vivos", "aves vivas", "cavalo manga larga",
    "gado", "bezerro", "ovelha", "suino", "pintinho", "galinha poedeira",
]

ML_BLOCKED_PROHIBITED_CATEGORIES: List[str] = [
    "ingresso ", "ingressos ", "passagem aerea", "pacote de viagem", "diaria de hotel",
    "aluguel de imovel", "aluguel de apartamento", "aluguel de casa", "aluguel de sala",
    "aluguel de kitnet", "apartamento a venda", "casa a venda", "terreno a venda",
    "loteamento", "fazenda a venda", "sitio a venda", "servico de ", "consultoria ",
    "curso online", "mentoria ", "assinatura mensal", "conta compartilhada",
    "emprestimo", "financiamento", "consorcio", "seguro auto", "seguro de vida",
    "carro usado", "carro 0km", "moto 0km", "motocicleta usada", "caminhao", "trator agricola",
    "colheitadeira", "semente de soja", "fertilizante agricola", "herbicida", "inseticida agricola",
    "agropecuario", "pulverizador agricola", "ordenha mecanica",
    "dvd original", "blu-ray", "cd musical", "disco de vinil", "lp vinil", "fita vhs",
    "torno mecanico industrial", "prensa hidraulica industrial", "empilhadeira",
    "balcao frigorifico comercial", "forno industrial padaria", "maquina industrial",
]

ML_GENERIC_URL_PATTERNS: List[str] = [
    r"^https?://(?:www\.)?mercadolivre\.com\.br/?$",
    r"mercadoshops\.com\.br",
    r"mercadolivre\.com\.br/(?:categorias|cart|checkout|my-account|minha-conta|compras|favoritos|clips|vendedores|perfil|emprestimos|mercado-credito|assinaturas)(?:/|$|\?)",
    r"mercadolivre\.com\.br/gz/",
    r"mercadolivre\.com\.br/jm/",
]

BLOCKED_JUNK_KEYWORDS: List[str] = ML_BLOCKED_MEDICAL_PHARMA + [
    "absorvente",
    "protetor diario",
    "carefree",
    "coletor menstrual",
    "papel higienico",
    "base glicerinada",
    "pastilha bendita canfora",
]
