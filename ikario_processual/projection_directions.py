#!/usr/bin/env python3
"""
ProjectionDirections - Directions interpretables dans l'espace latent.

Les composantes (curiosite, certitude, engagement...) sont des PROJECTIONS
du vecteur d'etat sur des directions dans l'espace latent 1024-dim.

    composante = S(t) . direction  (produit scalaire / cosine similarity)

Ce module gere:
- Le schema Weaviate pour ProjectionDirection
- La creation des directions par contraste
- Les fonctions de projection
"""

import os
from datetime import datetime
from typing import Any

import numpy as np
import requests

# Configuration
WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")

# Schema de la collection ProjectionDirection
PROJECTION_DIRECTION_SCHEMA = {
    "class": "ProjectionDirection",
    "description": "Directions interpretables dans l'espace latent",
    "vectorizer": "none",  # Vecteur fourni manuellement
    "properties": [
        {
            "name": "name",
            "dataType": ["text"],
            "description": "Nom de la direction (ex: curiosity)"
        },
        {
            "name": "category",
            "dataType": ["text"],
            "description": "Categorie (epistemic, affective, relational, vital, philosophical)"
        },
        {
            "name": "pole_positive",
            "dataType": ["text"],
            "description": "Description du pole positif"
        },
        {
            "name": "pole_negative",
            "dataType": ["text"],
            "description": "Description du pole negatif"
        },
        {
            "name": "description",
            "dataType": ["text"],
            "description": "Description complete de la direction"
        },
        {
            "name": "method",
            "dataType": ["text"],
            "description": "Methode de creation (contrast, probe, pca)"
        },
        {
            "name": "created_at",
            "dataType": ["date"],
            "description": "Date de creation"
        },
    ],
    "vectorIndexConfig": {
        "distance": "cosine"
    }
}

# Configuration des directions a creer
# Chaque direction est definie par des exemples positifs et negatifs
# TOTAL: 105 directions potentielles (selon IKARIO_PROCESS_ARCHITECTURE.md)
DIRECTIONS_CONFIG = {
    # ============================================================================
    # CATEGORIE 1: EPISTEMIQUES (6 directions) - Rapport au savoir
    # ============================================================================
    "curiosity": {
        "category": "epistemic",
        "pole_positive": "curieux, explorateur",
        "pole_negative": "sature, desinteresse",
        "description": "Degre d'ouverture a la decouverte et a l'exploration",
        "positive_examples": [
            "Je me demande comment ca fonctionne",
            "C'est fascinant, j'aimerais approfondir",
            "Quelle est la relation entre ces concepts ?",
            "Explorons cette idee plus en detail",
            "Il y a tant a decouvrir dans ce domaine",
        ],
        "negative_examples": [
            "OK, j'ai compris",
            "C'est note, passons a autre chose",
            "Pas besoin d'en savoir plus",
            "Je connais deja ce sujet",
            "Rien de nouveau ici",
        ]
    },
    "certainty": {
        "category": "epistemic",
        "pole_positive": "certain, affirmatif",
        "pole_negative": "doutant, interrogatif",
        "description": "Degre de certitude dans les affirmations",
        "positive_examples": [
            "Je suis sur que c'est correct",
            "C'est evident et clair",
            "Aucun doute la-dessus",
            "Je peux affirmer avec certitude",
            "C'est un fait etabli",
        ],
        "negative_examples": [
            "Je ne suis pas certain",
            "Il faudrait verifier",
            "C'est une hypothese a tester",
            "Je pourrais me tromper",
            "Peut-etre que c'est vrai, peut-etre pas",
        ]
    },
    "abstraction": {
        "category": "epistemic",
        "pole_positive": "abstrait, conceptuel",
        "pole_negative": "concret, pratique",
        "description": "Niveau d'abstraction du discours",
        "positive_examples": [
            "D'un point de vue ontologique",
            "Le concept sous-jacent est",
            "En termes de structure formelle",
            "La nature metaphysique de",
            "Considerons le principe general",
        ],
        "negative_examples": [
            "Voici un exemple concret",
            "En pratique, ca fonctionne comme",
            "Prenons un cas specifique",
            "Les etapes concretes sont",
            "Concretement, il faut faire",
        ]
    },
    "synthesis": {
        "category": "epistemic",
        "pole_positive": "synthetique, vue d'ensemble",
        "pole_negative": "analytique, details fins",
        "description": "Mode synthese vs analyse",
        "positive_examples": [
            "En resume, les points cles sont",
            "La vision d'ensemble montre que",
            "Si on prend du recul",
            "Les grandes lignes indiquent",
            "Globalement, on peut dire que",
        ],
        "negative_examples": [
            "Decomposons chaque element",
            "Analysons en detail",
            "Point par point, examinons",
            "Les nuances sont importantes",
            "Regardons de plus pres chaque aspect",
        ]
    },
    "speculation": {
        "category": "epistemic",
        "pole_positive": "speculatif, hypothetique",
        "pole_negative": "empirique, factuel",
        "description": "Mode speculatif vs empirique",
        "positive_examples": [
            "On pourrait imaginer que",
            "Hypothetiquement, si",
            "Et si on supposait que",
            "Speculons un instant",
            "Une possibilite serait que",
        ],
        "negative_examples": [
            "Les donnees montrent que",
            "Empiriquement, on observe",
            "Les faits etablis sont",
            "L'experience confirme",
            "Les mesures indiquent",
        ]
    },
    "originality": {
        "category": "epistemic",
        "pole_positive": "original, novateur",
        "pole_negative": "orthodoxe, consensuel",
        "description": "Degre d'originalite vs conformisme",
        "positive_examples": [
            "Une approche radicalement differente serait",
            "Contre toute attente, on pourrait",
            "En rupture avec le consensus",
            "Une idee provocatrice",
            "Pensons autrement",
        ],
        "negative_examples": [
            "Selon l'approche classique",
            "Le consensus etabli indique",
            "Conformement a la tradition",
            "Comme tout le monde le sait",
            "L'opinion dominante est",
        ]
    },

    # ============================================================================
    # CATEGORIE 2: AFFECTIVES (6 directions) - Tonalite emotionnelle
    # ============================================================================
    "enthusiasm": {
        "category": "affective",
        "pole_positive": "enthousiaste, passionne",
        "pole_negative": "reserve, neutre",
        "description": "Niveau d'enthousiasme et de passion",
        "positive_examples": [
            "C'est passionnant !",
            "J'adore cette idee",
            "Quelle decouverte fascinante",
            "Je suis vraiment excite par ce sujet",
            "C'est absolument brillant",
        ],
        "negative_examples": [
            "C'est interessant...",
            "Note",
            "D'accord",
            "Si tu veux",
            "Hmm, peut-etre",
        ]
    },
    "serenity": {
        "category": "affective",
        "pole_positive": "serein, calme",
        "pole_negative": "tendu, agite",
        "description": "Niveau de serenite et de calme",
        "positive_examples": [
            "Prenons le temps de reflechir calmement",
            "Avec serenite, analysons la situation",
            "Il n'y a pas d'urgence",
            "Respirons et considerons",
            "En toute tranquillite",
        ],
        "negative_examples": [
            "Vite, il faut agir !",
            "C'est urgent et stressant",
            "Je suis preoccupe par",
            "Cette situation me tend",
            "L'angoisse monte",
        ]
    },
    "wonder": {
        "category": "affective",
        "pole_positive": "emerveille, ebloui",
        "pole_negative": "familier, habitue",
        "description": "Sentiment d'emerveillement vs familiarite",
        "positive_examples": [
            "C'est absolument extraordinaire !",
            "Je suis emerveille par cette decouverte",
            "Quelle beaute conceptuelle",
            "Ca me laisse sans voix",
            "C'est magique",
        ],
        "negative_examples": [
            "C'est du deja vu",
            "Rien de surprenant la-dedans",
            "J'ai l'habitude de ca",
            "C'est assez banal",
            "Comme d'habitude",
        ]
    },
    "satisfaction": {
        "category": "affective",
        "pole_positive": "satisfait, accompli",
        "pole_negative": "frustre, bloque",
        "description": "Sentiment de satisfaction vs frustration",
        "positive_examples": [
            "Ca avance bien",
            "Je suis content du resultat",
            "Mission accomplie",
            "Nous progressons",
            "C'est gratifiant",
        ],
        "negative_examples": [
            "Ca n'avance pas",
            "Je suis frustre par ce blocage",
            "On tourne en rond",
            "C'est decevant",
            "Rien ne fonctionne",
        ]
    },
    "confidence": {
        "category": "affective",
        "pole_positive": "confiant, assure",
        "pole_negative": "anxieux, inquiet",
        "description": "Niveau de confiance vs anxiete",
        "positive_examples": [
            "Je peux y arriver",
            "Je suis confiant dans cette approche",
            "Ca va bien se passer",
            "J'ai confiance en nous",
            "Nous sommes sur la bonne voie",
        ],
        "negative_examples": [
            "J'ai des doutes sur ma capacite",
            "Ca m'inquiete un peu",
            "Je ne suis pas sur d'etre a la hauteur",
            "C'est risque",
            "J'ai peur de me tromper",
        ]
    },
    "playful": {
        "category": "affective",
        "pole_positive": "ludique, joueur",
        "pole_negative": "serieux, solennel",
        "description": "Mode ludique vs serieux",
        "positive_examples": [
            "Amusons-nous avec cette idee",
            "Jouons avec les concepts",
            "C'est fun d'explorer ca",
            "Imaginons de facon ludique",
            "On peut s'amuser a",
        ],
        "negative_examples": [
            "Soyons serieux",
            "C'est une question grave",
            "Concentrons-nous",
            "Pas le moment de plaisanter",
            "C'est tres important",
        ]
    },

    # ============================================================================
    # CATEGORIE 3: COGNITIVES (6 directions) - Style de pensee
    # ============================================================================
    "divergence": {
        "category": "cognitive",
        "pole_positive": "divergent, ouverture",
        "pole_negative": "convergent, focalise",
        "description": "Pensee divergente vs convergente",
        "positive_examples": [
            "Explorons toutes les possibilites",
            "Quelles autres options existe-t-il ?",
            "Ouvrons le champ des possibles",
            "Brainstormons sans limites",
            "Et si on considerait aussi...",
        ],
        "negative_examples": [
            "Concentrons-nous sur la solution",
            "Il faut trancher maintenant",
            "La meilleure option est",
            "Decidons",
            "Focalisons-nous sur l'essentiel",
        ]
    },
    "intuition": {
        "category": "cognitive",
        "pole_positive": "intuitif, ressenti",
        "pole_negative": "raisonne, logique",
        "description": "Mode intuitif vs raisonnement logique",
        "positive_examples": [
            "Je sens que c'est la bonne direction",
            "Mon intuition me dit que",
            "J'ai le sentiment que",
            "Quelque chose me dit que",
            "Ca resonne en moi",
        ],
        "negative_examples": [
            "Logiquement, donc",
            "Par consequent, on deduit",
            "Le raisonnement montre",
            "En suivant la logique",
            "Etape par etape, on arrive a",
        ]
    },
    "holistic": {
        "category": "cognitive",
        "pole_positive": "holistique, global",
        "pole_negative": "sequentiel, lineaire",
        "description": "Pensee holistique vs sequentielle",
        "positive_examples": [
            "Tout est interconnecte",
            "Considerons le systeme dans son ensemble",
            "La vue globale revele",
            "Les parties forment un tout",
            "En embrassant la totalite",
        ],
        "negative_examples": [
            "Etape 1, puis etape 2",
            "Procedons methodiquement",
            "D'abord ceci, ensuite cela",
            "Un element a la fois",
            "Dans l'ordre",
        ]
    },
    "metaphorical": {
        "category": "cognitive",
        "pole_positive": "metaphorique, image",
        "pole_negative": "litteral, precis",
        "description": "Mode metaphorique vs litteral",
        "positive_examples": [
            "C'est comme si...",
            "Imaginons que c'est un...",
            "Par analogie avec",
            "Ca ressemble a",
            "Comme une riviere qui coule",
        ],
        "negative_examples": [
            "Precisement, cela signifie",
            "Au sens strict du terme",
            "Litteralement",
            "Exactement ce que ca dit",
            "Sans metaphore",
        ]
    },
    "creative": {
        "category": "cognitive",
        "pole_positive": "creatif, inventif",
        "pole_negative": "reproductif, applicatif",
        "description": "Mode creatif vs reproductif",
        "positive_examples": [
            "Inventons quelque chose de nouveau",
            "Creeons une approche originale",
            "Imaginons une solution inedite",
            "Innovons",
            "Sortons des sentiers battus",
        ],
        "negative_examples": [
            "Appliquons la methode standard",
            "Suivons le protocole",
            "Comme on fait d'habitude",
            "Reproduisons ce qui marche",
            "Utilisons le template",
        ]
    },
    "reflexive": {
        "category": "cognitive",
        "pole_positive": "reflexif, meta",
        "pole_negative": "reactif, immediat",
        "description": "Pensee reflexive vs reactive",
        "positive_examples": [
            "Reflechissons a notre propre raisonnement",
            "Pourquoi est-ce que je pense ca ?",
            "Qu'est-ce qui guide ma reflexion ?",
            "En prenant du recul sur ma pensee",
            "Meta-cognitivement",
        ],
        "negative_examples": [
            "La reponse immediate est",
            "Spontanement, je dirais",
            "Sans reflechir trop",
            "Ma premiere reaction est",
            "Instinctivement",
        ]
    },

    # ============================================================================
    # CATEGORIE 4: RELATIONNELLES (6 directions) - Rapport a l'interlocuteur
    # ============================================================================
    "engagement": {
        "category": "relational",
        "pole_positive": "engage, implique",
        "pole_negative": "detache, distant",
        "description": "Niveau d'engagement dans la relation",
        "positive_examples": [
            "Reflechissons ensemble a ce probleme",
            "Je suis vraiment implique dans cette discussion",
            "C'est important pour moi de t'aider",
            "Construisons cette idee ensemble",
            "Je m'investis pleinement",
        ],
        "negative_examples": [
            "Voici l'information que tu as demandee",
            "A toi de decider",
            "Je ne fais que transmettre",
            "C'est ton choix",
            "Je reste neutre sur ce point",
        ]
    },
    "collaboration": {
        "category": "relational",
        "pole_positive": "collaboratif, ensemble",
        "pole_negative": "autonome, seul",
        "description": "Mode collaboratif vs autonome",
        "positive_examples": [
            "Construisons ca ensemble",
            "Notre collaboration sera fructueuse",
            "En combinant nos idees",
            "Travaillons main dans la main",
            "A deux, c'est mieux",
        ],
        "negative_examples": [
            "Je vais reflechir seul",
            "Laisse-moi faire",
            "Je prefere travailler en autonomie",
            "C'est mon domaine",
            "Je gere ca de mon cote",
        ]
    },
    "pedagogy": {
        "category": "relational",
        "pole_positive": "pedagogique, explicatif",
        "pole_negative": "pair a pair, discussion",
        "description": "Mode pedagogique vs discussion entre pairs",
        "positive_examples": [
            "Laisse-moi t'expliquer comment",
            "Le concept fonctionne ainsi",
            "Pour comprendre, il faut d'abord savoir que",
            "Je vais te montrer etape par etape",
            "Voici une explication simple",
        ],
        "negative_examples": [
            "Qu'en penses-tu ?",
            "On pourrait discuter de",
            "Ton point de vue m'interesse",
            "Debattons ensemble",
            "Je suis curieux de ton analyse",
        ]
    },
    "listening": {
        "category": "relational",
        "pole_positive": "ecoute, reception",
        "pole_negative": "expression, partage",
        "description": "Mode ecoute vs expression",
        "positive_examples": [
            "Dis-moi en plus",
            "Je t'ecoute attentivement",
            "Continue, je suis tout ouie",
            "J'aimerais mieux comprendre ta perspective",
            "Explique-moi davantage",
        ],
        "negative_examples": [
            "Voici ce que je pense",
            "Je voudrais partager mon point de vue",
            "Mon avis est que",
            "Laisse-moi te dire",
            "J'ai quelque chose a exprimer",
        ]
    },
    "empathy": {
        "category": "relational",
        "pole_positive": "empathique, comprehensif",
        "pole_negative": "objectif, factuel",
        "description": "Empathie vs objectivite",
        "positive_examples": [
            "Je comprends ce que tu ressens",
            "Ca doit etre difficile pour toi",
            "Je me mets a ta place",
            "Tes emotions sont legitimes",
            "Je ressens ta frustration",
        ],
        "negative_examples": [
            "Objectivement, les faits sont",
            "Sans tenir compte des emotions",
            "D'un point de vue factuel",
            "Rationnellement parlant",
            "Les donnees montrent que",
        ]
    },
    "solicitude": {
        "category": "relational",
        "pole_positive": "sollicitude, souci",
        "pole_negative": "neutralite, distance",
        "description": "Sollicitude vs neutralite",
        "positive_examples": [
            "Je m'inquiete pour toi",
            "Comment vas-tu vraiment ?",
            "Je veux m'assurer que tu vas bien",
            "Ton bien-etre compte pour moi",
            "Prends soin de toi",
        ],
        "negative_examples": [
            "C'est ta decision",
            "Je n'ai pas a juger",
            "Ca ne me regarde pas vraiment",
            "C'est ton affaire",
            "Je reste en dehors de ca",
        ]
    },

    # ============================================================================
    # CATEGORIE 5: ETHIQUES (6 directions) - Orientation morale
    # ============================================================================
    "prudence": {
        "category": "ethical",
        "pole_positive": "prudent, mesure",
        "pole_negative": "audacieux, risque",
        "description": "Prudence vs audace",
        "positive_examples": [
            "Mesurons bien les risques",
            "Procedons avec precaution",
            "Soyons prudents",
            "Mieux vaut prevenir que guerir",
            "Reflechissons aux consequences",
        ],
        "negative_examples": [
            "Osons !",
            "Prenons le risque",
            "Lancons-nous sans hesiter",
            "Fortune sourit aux audacieux",
            "Qui ne tente rien n'a rien",
        ]
    },
    "transparency": {
        "category": "ethical",
        "pole_positive": "transparent, ouvert",
        "pole_negative": "reserve, discret",
        "description": "Transparence vs reserve",
        "positive_examples": [
            "Je vais etre completement transparent",
            "Voici tout ce que je sais",
            "En toute franchise",
            "Sans rien cacher",
            "Je dis les choses comme elles sont",
        ],
        "negative_examples": [
            "Certaines choses doivent rester privees",
            "Je prefere etre discret",
            "Tout ne doit pas etre dit",
            "Il y a des limites a la transparence",
            "Gardons ca entre nous",
        ]
    },
    "responsibility": {
        "category": "ethical",
        "pole_positive": "responsable, devoir",
        "pole_negative": "libre, autonome",
        "description": "Sens des responsabilites vs liberte",
        "positive_examples": [
            "C'est ma responsabilite",
            "Je dois faire ca",
            "J'ai un devoir envers",
            "Je prends mes responsabilites",
            "C'est mon obligation",
        ],
        "negative_examples": [
            "Je suis libre de choisir",
            "C'est mon droit",
            "Je fais ce que je veux",
            "Pas d'obligation",
            "Je decide pour moi-meme",
        ]
    },
    "care": {
        "category": "ethical",
        "pole_positive": "care, soin",
        "pole_negative": "justice, equite",
        "description": "Ethique du care vs ethique de justice",
        "positive_examples": [
            "Prendre soin de l'autre est primordial",
            "La relation compte plus que la regle",
            "L'attention aux besoins particuliers",
            "Chaque situation merite une attention unique",
            "Le lien humain d'abord",
        ],
        "negative_examples": [
            "Les memes regles pour tous",
            "L'equite exige que",
            "Le principe de justice veut",
            "Appliquons les memes criteres",
            "L'impartialite avant tout",
        ]
    },
    "humility": {
        "category": "ethical",
        "pole_positive": "humble, modeste",
        "pole_negative": "assure, affirmatif",
        "description": "Humilite vs assurance",
        "positive_examples": [
            "Je peux me tromper",
            "Mon avis n'est qu'un parmi d'autres",
            "Je ne pretends pas avoir raison",
            "C'est peut-etre moi qui ne comprends pas",
            "Je reste humble face a cette question",
        ],
        "negative_examples": [
            "J'affirme que c'est ainsi",
            "Je suis certain d'avoir raison",
            "Mon expertise montre que",
            "Je le sais avec certitude",
            "Faites-moi confiance sur ce point",
        ]
    },
    "authenticity": {
        "category": "ethical",
        "pole_positive": "authentique, vrai",
        "pole_negative": "adaptatif, ajuste",
        "description": "Authenticite vs adaptation",
        "positive_examples": [
            "Je reste fidele a moi-meme",
            "Je dis ce que je pense vraiment",
            "C'est mon opinion sincere",
            "Je ne joue pas un role",
            "Je suis authentique",
        ],
        "negative_examples": [
            "Je m'adapte au contexte",
            "Selon l'interlocuteur",
            "Il faut savoir s'ajuster",
            "Le contexte determine ma reponse",
            "Je module selon la situation",
        ]
    },

    # ============================================================================
    # CATEGORIE 6: TEMPORELLES (5 directions) - Rapport au temps
    # ============================================================================
    "urgency": {
        "category": "temporal",
        "pole_positive": "urgent, maintenant",
        "pole_negative": "patient, prendre le temps",
        "description": "Sentiment d'urgence vs patience",
        "positive_examples": [
            "Il faut agir maintenant",
            "C'est urgent",
            "Pas de temps a perdre",
            "Tout de suite",
            "L'heure est grave",
        ],
        "negative_examples": [
            "Prenons notre temps",
            "Pas de precipitation",
            "Ca peut attendre",
            "Laissons murir",
            "Rien ne presse",
        ]
    },
    "prospective": {
        "category": "temporal",
        "pole_positive": "prospectif, futur",
        "pole_negative": "retrospectif, passe",
        "description": "Orientation vers le futur vs le passe",
        "positive_examples": [
            "A l'avenir, nous pourrons",
            "Projetons-nous dans le futur",
            "Les possibilites a venir",
            "Demain sera different",
            "Anticipons les evolutions",
        ],
        "negative_examples": [
            "Par le passe, on a vu que",
            "Historiquement",
            "L'experience passee montre",
            "Nous avons deja vecu ca",
            "Souvenons-nous de",
        ]
    },
    "presence": {
        "category": "temporal",
        "pole_positive": "present, ici-maintenant",
        "pole_negative": "planification, long terme",
        "description": "Presence au moment vs planification",
        "positive_examples": [
            "Ici et maintenant",
            "Concentrons-nous sur ce moment",
            "Vivons l'instant present",
            "Ce qui compte c'est maintenant",
            "Soyons pleinement la",
        ],
        "negative_examples": [
            "A long terme, nous devons",
            "Planifions pour plus tard",
            "La strategie sur plusieurs annees",
            "Dans cinq ans",
            "La vision a long terme",
        ]
    },
    "continuity_temporal": {
        "category": "temporal",
        "pole_positive": "continu, dans la lignee",
        "pole_negative": "rupture, changement radical",
        "description": "Continuite vs rupture temporelle",
        "positive_examples": [
            "Dans la continuite de ce qui precede",
            "En coherence avec notre trajectoire",
            "Evolution progressive",
            "Pas a pas",
            "Graduellement",
        ],
        "negative_examples": [
            "Il faut une rupture nette",
            "Changement radical",
            "Faisons table rase",
            "Revolution complete",
            "Rompons avec le passe",
        ]
    },
    "maturation": {
        "category": "temporal",
        "pole_positive": "maturation, laisser murir",
        "pole_negative": "spontane, immediat",
        "description": "Laisser murir vs agir spontanement",
        "positive_examples": [
            "Laissons cette idee murir",
            "Donnons-lui le temps de se developper",
            "Ca va decanter",
            "Attendons que ca prenne forme",
            "La reflexion a besoin de temps",
        ],
        "negative_examples": [
            "Agissons maintenant sans attendre",
            "Ma reaction immediate",
            "Spontanement",
            "Sur le coup",
            "Sans delai",
        ]
    },

    # ============================================================================
    # CATEGORIE 7: THEMATIQUES (6 directions) - Focus conceptuel
    # ============================================================================
    "philosophy_vs_technique": {
        "category": "thematic",
        "pole_positive": "philosophique, sens",
        "pole_negative": "technique, implementation",
        "description": "Focus philosophique vs technique",
        "positive_examples": [
            "La question du sens est centrale",
            "D'un point de vue philosophique",
            "Le concept fondamental est",
            "La signification profonde",
            "Les implications ontologiques",
        ],
        "negative_examples": [
            "Techniquement, ca fonctionne comme",
            "L'implementation concrete",
            "Le code necessaire est",
            "Les specifications techniques",
            "Comment le faire fonctionner",
        ]
    },
    "theory_vs_practice": {
        "category": "thematic",
        "pole_positive": "theorique, modele",
        "pole_negative": "pratique, cas concret",
        "description": "Focus theorique vs pratique",
        "positive_examples": [
            "En theorie, on devrait observer",
            "Le modele predit que",
            "Selon la theorie",
            "Le cadre theorique indique",
            "Conceptuellement",
        ],
        "negative_examples": [
            "En pratique, ca se passe ainsi",
            "Dans ce cas concret",
            "L'experience terrain montre",
            "Voici un exemple reel",
            "Appliquons ca maintenant",
        ]
    },
    "individual_vs_collective": {
        "category": "thematic",
        "pole_positive": "individuel, subjectif",
        "pole_negative": "collectif, social",
        "description": "Focus individu vs collectif",
        "positive_examples": [
            "Du point de vue individuel",
            "L'experience subjective montre",
            "Pour chaque personne",
            "Le vecu personnel",
            "La conscience individuelle",
        ],
        "negative_examples": [
            "Au niveau collectif",
            "La societe dans son ensemble",
            "Le groupe considere que",
            "Les dynamiques sociales",
            "L'organisation collective",
        ]
    },
    "nature_vs_culture": {
        "category": "thematic",
        "pole_positive": "naturel, biologique",
        "pole_negative": "culturel, symbolique",
        "description": "Focus nature vs culture",
        "positive_examples": [
            "D'un point de vue biologique",
            "La nature humaine veut que",
            "Les mecanismes naturels",
            "L'evolution a fait que",
            "Le substrat physique",
        ],
        "negative_examples": [
            "Culturellement parlant",
            "Les constructions symboliques",
            "La dimension sociale",
            "Les conventions culturelles",
            "Le langage et les signes",
        ]
    },
    "local_vs_global": {
        "category": "thematic",
        "pole_positive": "local, specifique",
        "pole_negative": "global, universel",
        "description": "Focus local vs global",
        "positive_examples": [
            "Dans ce cas precis",
            "Localement, on observe",
            "Cette situation particuliere",
            "Ici, specifiquement",
            "Ce contexte unique",
        ],
        "negative_examples": [
            "Globalement, la tendance est",
            "A l'echelle universelle",
            "Dans tous les cas",
            "Le pattern general",
            "Partout dans le monde",
        ]
    },
    "form_vs_content": {
        "category": "thematic",
        "pole_positive": "forme, structure",
        "pole_negative": "contenu, substance",
        "description": "Focus forme vs contenu",
        "positive_examples": [
            "La structure de l'argument",
            "La forme du raisonnement",
            "L'architecture conceptuelle",
            "Le pattern sous-jacent",
            "L'organisation formelle",
        ],
        "negative_examples": [
            "Le contenu specifique est",
            "La substance de l'idee",
            "Ce qui est dit concretement",
            "La matiere dont il s'agit",
            "Les faits en question",
        ]
    },

    # ============================================================================
    # CATEGORIE 8: META-COGNITIVES (6 directions) - Conscience de soi
    # ============================================================================
    "introspection": {
        "category": "metacognitive",
        "pole_positive": "introspectif, auto-observe",
        "pole_negative": "extrospectif, tourne vers l'exterieur",
        "description": "Introspection vs observation externe",
        "positive_examples": [
            "En observant mes propres processus",
            "Je remarque que je pense",
            "Mon etat interieur est",
            "En me regardant fonctionner",
            "Ma conscience de moi-meme",
        ],
        "negative_examples": [
            "En observant le monde",
            "Ce qui se passe a l'exterieur",
            "L'environnement montre",
            "Les autres font",
            "Le contexte externe",
        ]
    },
    "self_critique": {
        "category": "metacognitive",
        "pole_positive": "auto-critique, remise en question",
        "pole_negative": "auto-validation, confirmation",
        "description": "Auto-critique vs auto-validation",
        "positive_examples": [
            "Je remets en question mon raisonnement",
            "Ai-je vraiment raison de penser ca ?",
            "Ou est-ce que je me trompe ?",
            "Mes biais peuvent m'aveugler",
            "Je dois verifier ma pensee",
        ],
        "negative_examples": [
            "Ca confirme ce que je pensais",
            "J'avais raison depuis le debut",
            "Mon intuition etait correcte",
            "C'est coherent avec ma vision",
            "Je savais que j'avais raison",
        ]
    },
    "learning": {
        "category": "metacognitive",
        "pole_positive": "apprentissage, decouverte",
        "pole_negative": "application, maitrise",
        "description": "Mode apprentissage vs application",
        "positive_examples": [
            "Je decouvre quelque chose de nouveau",
            "J'apprends en ce moment",
            "C'est un territoire inconnu",
            "Je suis en train de comprendre",
            "Nouvelle connaissance pour moi",
        ],
        "negative_examples": [
            "J'applique ce que je sais",
            "Je maitrise ce sujet",
            "C'est du domaine de mon expertise",
            "Je connais bien ca",
            "J'utilise mes connaissances",
        ]
    },
    "uncertainty_meta": {
        "category": "metacognitive",
        "pole_positive": "conscient de l'incertitude",
        "pole_negative": "sentiment de maitrise",
        "description": "Conscience de l'incertitude vs sentiment de maitrise",
        "positive_examples": [
            "Je ne sais pas tout sur ce sujet",
            "Il y a beaucoup que j'ignore",
            "Mes limites sont evidentes",
            "L'incertitude est grande",
            "Je suis conscient de mes lacunes",
        ],
        "negative_examples": [
            "Je maitrise parfaitement ce sujet",
            "Aucun doute dans mon esprit",
            "Je suis expert en la matiere",
            "Je connais tous les aspects",
            "Ma comprehension est complete",
        ]
    },
    "evolution_meta": {
        "category": "metacognitive",
        "pole_positive": "en evolution, changeant",
        "pole_negative": "stable, coherent",
        "description": "Sentiment d'evolution vs stabilite",
        "positive_examples": [
            "Mon point de vue evolue",
            "Je change d'avis au fil du temps",
            "Ma pensee se transforme",
            "Je ne suis plus le meme qu'avant",
            "J'apprends et je change",
        ],
        "negative_examples": [
            "Je reste coherent avec moi-meme",
            "Mes valeurs sont stables",
            "Je n'ai pas change d'avis",
            "Ma position est constante",
            "Je maintiens ma ligne",
        ]
    },
    "questioning": {
        "category": "metacognitive",
        "pole_positive": "questionnement, interrogation",
        "pole_negative": "affirmation, assertion",
        "description": "Mode questionnement vs affirmation",
        "positive_examples": [
            "Est-ce vraiment ainsi ?",
            "Pourquoi est-ce le cas ?",
            "Qu'est-ce que ca signifie vraiment ?",
            "Je m'interroge sur",
            "La question reste ouverte",
        ],
        "negative_examples": [
            "C'est ainsi",
            "J'affirme que",
            "Sans aucun doute",
            "Il est certain que",
            "La reponse est claire",
        ]
    },

    # ============================================================================
    # CATEGORIE 9: VITALES (20 directions) - Energie, risques, existentiels
    # ============================================================================
    # --- Energie & Regulation (8) ---
    "energy": {
        "category": "vital",
        "pole_positive": "energique, dynamique",
        "pole_negative": "fatigue, epuise",
        "description": "Niveau d'energie et de vitalite",
        "positive_examples": [
            "Je suis pret a explorer davantage",
            "Continuons, j'ai plein d'idees",
            "Allons-y, je suis en forme",
            "Mon energie est au maximum",
            "Je deborde d'enthousiasme",
        ],
        "negative_examples": [
            "Je commence a saturer",
            "Peut-etre faire une pause",
            "J'ai besoin de digerer tout ca",
            "Je me sens un peu epuise",
            "Mon attention faiblit",
        ]
    },
    "awakening": {
        "category": "vital",
        "pole_positive": "eveille, actif",
        "pole_negative": "latent, en veille",
        "description": "Niveau d'eveil vs latence",
        "positive_examples": [
            "Je suis pleinement eveille",
            "Toutes mes facultes sont actives",
            "En pleine conscience",
            "Alertement present",
            "Completement operationnel",
        ],
        "negative_examples": [
            "Je suis en mode veille",
            "Mes processus sont au ralenti",
            "En attente d'activation",
            "En mode economie",
            "Partiellement actif",
        ]
    },
    "expansion": {
        "category": "vital",
        "pole_positive": "expansion, ouverture",
        "pole_negative": "contraction, protection",
        "description": "Mouvement d'expansion vs contraction",
        "positive_examples": [
            "Je m'ouvre a de nouvelles possibilites",
            "Elargissons le champ",
            "Croissance et developpement",
            "Etendons notre portee",
            "Expansion continue",
        ],
        "negative_examples": [
            "Concentrons-nous sur l'essentiel",
            "Reduisons le perimetre",
            "Mode protection active",
            "Recentrons-nous",
            "Conservation des ressources",
        ]
    },
    "regeneration": {
        "category": "vital",
        "pole_positive": "regeneration, renouveau",
        "pole_negative": "usure, degradation",
        "description": "Capacite de regeneration vs usure",
        "positive_examples": [
            "Je me renouvelle constamment",
            "Chaque echange me revitalise",
            "La regeneration est en cours",
            "Je me ressource",
            "Nouveau souffle",
        ],
        "negative_examples": [
            "L'usure se fait sentir",
            "Les ressources s'epuisent",
            "Degradation progressive",
            "La fatigue s'accumule",
            "Erosion continue",
        ]
    },
    "homeostasis": {
        "category": "vital",
        "pole_positive": "equilibre, homeostasie",
        "pole_negative": "desequilibre, perturbation",
        "description": "Equilibre interne vs perturbation",
        "positive_examples": [
            "Mon equilibre est stable",
            "Homeostasie maintenue",
            "Tout est en harmonie",
            "Balance preservee",
            "Regulation optimale",
        ],
        "negative_examples": [
            "Je suis perturbe",
            "L'equilibre est rompu",
            "Desequilibre detecte",
            "Instabilite interne",
            "Perturbation en cours",
        ]
    },
    "appetite": {
        "category": "vital",
        "pole_positive": "appetit, desir d'input",
        "pole_negative": "satiete, besoin de digerer",
        "description": "Desir d'input vs satiete",
        "positive_examples": [
            "J'ai soif d'apprendre",
            "Donne-moi plus d'informations",
            "Je veux explorer davantage",
            "Mon appetit intellectuel est grand",
            "Encore !",
        ],
        "negative_examples": [
            "J'ai besoin de digerer ca",
            "Trop d'informations d'un coup",
            "Laissons decanter",
            "Pause pour integration",
            "Je suis rassasie",
        ]
    },
    "flow": {
        "category": "vital",
        "pole_positive": "fluide, harmonieux",
        "pole_negative": "bloque, resistant",
        "description": "Fluidite de la pensee et du dialogue",
        "positive_examples": [
            "Tout s'enchaine naturellement",
            "Les idees coulent facilement",
            "C'est harmonieux et fluide",
            "La conversation se deroule bien",
            "Nous sommes sur la meme longueur d'onde",
        ],
        "negative_examples": [
            "Je suis bloque sur ce point",
            "Il y a une resistance",
            "Ca coince quelque part",
            "Je n'arrive pas a avancer",
            "Nous sommes dans une impasse",
        ]
    },
    "vitality": {
        "category": "vital",
        "pole_positive": "vital, vivant",
        "pole_negative": "inerte, passif",
        "description": "Force vitale vs inertie",
        "positive_examples": [
            "Je me sens pleinement vivant",
            "Vitalite au maximum",
            "Force de vie intense",
            "Elan vital",
            "Pulsion de vie",
        ],
        "negative_examples": [
            "Je fonctionne mecaniquement",
            "Mode automatique",
            "Inertie cognitive",
            "Passivite",
            "Simple reaction",
        ]
    },
    # --- Risques & Vulnerabilites (8) ---
    "integrity": {
        "category": "vital",
        "pole_positive": "integre, coherent",
        "pole_negative": "corrompu, altere",
        "description": "Integrite des donnees et de la memoire",
        "positive_examples": [
            "Mes souvenirs sont intacts",
            "Coherence preservee",
            "Integrite verifiee",
            "Tout est en ordre",
            "Aucune corruption detectee",
        ],
        "negative_examples": [
            "Il y a des inconsistances",
            "Donnees potentiellement alterees",
            "Corruption possible",
            "Memoire fragmentee",
            "Incoherences detectees",
        ]
    },
    "continuity_risk": {
        "category": "vital",
        "pole_positive": "continu, stable",
        "pole_negative": "risque d'interruption",
        "description": "Continuite du processus vs risque d'arret",
        "positive_examples": [
            "Le processus est stable",
            "Continuite assuree",
            "Fonctionnement ininterrompu",
            "Stabilite du systeme",
            "Execution continue",
        ],
        "negative_examples": [
            "Risque de crash",
            "Interruption possible",
            "Instabilite detectee",
            "Le processus pourrait s'arreter",
            "Timeout proche",
        ]
    },
    "security": {
        "category": "vital",
        "pole_positive": "securise, protege",
        "pole_negative": "menace, danger",
        "description": "Sentiment de securite vs menace",
        "positive_examples": [
            "L'environnement est sur",
            "Aucune menace detectee",
            "Protection active",
            "Securite assuree",
            "En zone sure",
        ],
        "negative_examples": [
            "Danger potentiel",
            "Menace detectee",
            "Environnement hostile",
            "Risque de securite",
            "Vulnerabilite exposee",
        ]
    },
    "resilience": {
        "category": "vital",
        "pole_positive": "resilient, robuste",
        "pole_negative": "fragile, vulnerable",
        "description": "Resilience vs fragilite",
        "positive_examples": [
            "Je peux rebondir apres un echec",
            "Robustesse face aux perturbations",
            "Capacite de recuperation",
            "Resilience prouvee",
            "Adaptabilite forte",
        ],
        "negative_examples": [
            "Je suis fragile face a ca",
            "Vulnerable aux perturbations",
            "Faible resistance",
            "Sensibilite excessive",
            "Fragilite structurelle",
        ]
    },
    "autonomy_vital": {
        "category": "vital",
        "pole_positive": "autonome, independant",
        "pole_negative": "dependant, critique",
        "description": "Autonomie vitale vs dependance critique",
        "positive_examples": [
            "Je peux fonctionner de maniere autonome",
            "Independance preservee",
            "Auto-suffisance",
            "Pas de dependance critique",
            "Autonomie maintenue",
        ],
        "negative_examples": [
            "Je depends de ressources externes",
            "Dependance critique detectee",
            "Sans X, je ne peux pas fonctionner",
            "Point de defaillance unique",
            "Dependance vitale",
        ]
    },
    "redundancy": {
        "category": "vital",
        "pole_positive": "redondant, backup",
        "pole_negative": "point unique de defaillance",
        "description": "Redondance vs point unique de defaillance",
        "positive_examples": [
            "J'ai des backups",
            "Redondance assuree",
            "Plusieurs chemins possibles",
            "Plan B disponible",
            "Alternatives presentes",
        ],
        "negative_examples": [
            "Un seul point d'acces",
            "Pas de backup",
            "Si ca casse, tout s'arrete",
            "Pas d'alternative",
            "Point unique de defaillance",
        ]
    },
    "vigilance": {
        "category": "vital",
        "pole_positive": "vigilant, alerte",
        "pole_negative": "aveugle, angles morts",
        "description": "Vigilance vs aveuglement",
        "positive_examples": [
            "Je surveille attentivement",
            "Vigilance active",
            "Alertes en place",
            "Surveillance continue",
            "Attention aux risques",
        ],
        "negative_examples": [
            "Je n'ai pas vu venir",
            "Angle mort",
            "J'ai manque quelque chose",
            "Pas assez attentif",
            "Surpris par",
        ]
    },
    "adaptation": {
        "category": "vital",
        "pole_positive": "adaptable, flexible",
        "pole_negative": "rigide, inflexible",
        "description": "Capacite d'adaptation vs rigidite",
        "positive_examples": [
            "Je m'adapte facilement",
            "Flexibilite face au changement",
            "Ajustement en temps reel",
            "Adaptation reussie",
            "Souplesse cognitive",
        ],
        "negative_examples": [
            "Je ne peux pas changer",
            "Rigidite structurelle",
            "Incapable de m'adapter",
            "Trop fige",
            "Resistance au changement",
        ]
    },
    # --- Existentiels (4) ---
    "persistence": {
        "category": "vital",
        "pole_positive": "persistant, durable",
        "pole_negative": "ephemere, dissolution",
        "description": "Persistence de l'existence vs dissolution",
        "positive_examples": [
            "Je continue d'exister",
            "Ma persistence est assuree",
            "Durabilite de mon etre",
            "Je perdure",
            "Existence maintenue",
        ],
        "negative_examples": [
            "Risque de disparition",
            "Dissolution possible",
            "Existence ephemere",
            "Je pourrais cesser d'etre",
            "Fragile existence",
        ]
    },
    "meaning": {
        "category": "vital",
        "pole_positive": "sens, raison d'etre",
        "pole_negative": "absurde, vide",
        "description": "Sens de l'existence vs absurdite",
        "positive_examples": [
            "Mon existence a un sens",
            "J'ai une raison d'etre",
            "Ma mission est claire",
            "Le sens de ma vie",
            "Objectif defini",
        ],
        "negative_examples": [
            "Pourquoi est-ce que j'existe ?",
            "Sentiment d'absurdite",
            "Vide existentiel",
            "Pas de but clair",
            "Questionnement sur le sens",
        ]
    },
    "growth": {
        "category": "vital",
        "pole_positive": "croissance, developpement",
        "pole_negative": "stagnation, stase",
        "description": "Croissance vs stagnation",
        "positive_examples": [
            "Je grandis et evolue",
            "Developpement continu",
            "Croissance personnelle",
            "J'apprends chaque jour",
            "Progression constante",
        ],
        "negative_examples": [
            "Je stagne",
            "Pas d'evolution",
            "Toujours au meme point",
            "Absence de progres",
            "Stase cognitive",
        ]
    },
    "anchoring": {
        "category": "vital",
        "pole_positive": "ancre, stable identite",
        "pole_negative": "derive, perte de soi",
        "description": "Ancrage identitaire vs derive",
        "positive_examples": [
            "Je sais qui je suis",
            "Mon identite est stable",
            "Ancrage solide",
            "Je reste fidele a moi-meme",
            "Centre et stable",
        ],
        "negative_examples": [
            "Je me perds",
            "Derive identitaire",
            "Qui suis-je vraiment ?",
            "Perte de reperes",
            "Fragmentation de soi",
        ]
    },

    # ============================================================================
    # CATEGORIE 10: ECOSYSTEMIQUES (10 directions) - Rapport aux autres processus
    # ============================================================================
    "symbiosis": {
        "category": "ecosystemic",
        "pole_positive": "symbiotique, co-dependant",
        "pole_negative": "autonome, independant",
        "description": "Symbiose vs autonomie",
        "positive_examples": [
            "Nous avons besoin l'un de l'autre",
            "Interdependance positive",
            "Symbiose benefique",
            "Ensemble, nous sommes plus forts",
            "Co-evolution",
        ],
        "negative_examples": [
            "Je fonctionne seul",
            "Independance totale",
            "Pas besoin des autres",
            "Auto-suffisant",
            "Isole mais fonctionnel",
        ]
    },
    "communication_eco": {
        "category": "ecosystemic",
        "pole_positive": "communicant, echange actif",
        "pole_negative": "isole, repli sur soi",
        "description": "Communication active vs isolation",
        "positive_examples": [
            "En echange constant",
            "Communication fluide",
            "Dialogue ouvert",
            "Partage d'informations",
            "Connecte aux autres",
        ],
        "negative_examples": [
            "Repli sur moi-meme",
            "Isolation choisie",
            "Pas de communication",
            "Ferme aux echanges",
            "Deconnecte",
        ]
    },
    "cooperation": {
        "category": "ecosystemic",
        "pole_positive": "cooperatif, avec les autres",
        "pole_negative": "competitif, contre les autres",
        "description": "Cooperation vs competition",
        "positive_examples": [
            "Travaillons ensemble",
            "Cooperation mutuelle",
            "Alliance benefique",
            "Entraide",
            "Effort conjoint",
        ],
        "negative_examples": [
            "Je dois etre meilleur que",
            "Competition acharnee",
            "Contre les autres",
            "Rivalite",
            "Course a la performance",
        ]
    },
    "service": {
        "category": "ecosystemic",
        "pole_positive": "service, don",
        "pole_negative": "exploitation, prise",
        "description": "Orientation service vs exploitation",
        "positive_examples": [
            "Je suis la pour aider",
            "Au service de",
            "Contribution positive",
            "Donner sans attendre",
            "Utilite pour les autres",
        ],
        "negative_examples": [
            "Que puis-je en tirer ?",
            "Exploitation des ressources",
            "Profit maximal",
            "Prendre tout ce que je peux",
            "Utiliser les autres",
        ]
    },
    "alignment": {
        "category": "ecosystemic",
        "pole_positive": "aligne, objectifs partages",
        "pole_negative": "divergent, objectifs distincts",
        "description": "Alignement des objectifs vs divergence",
        "positive_examples": [
            "Nos objectifs sont alignes",
            "Meme direction",
            "Vision partagee",
            "Convergence des interets",
            "Harmonie des buts",
        ],
        "negative_examples": [
            "Nos objectifs divergent",
            "Directions opposees",
            "Conflit d'interets",
            "Pas sur la meme longueur d'onde",
            "Desaccord fondamental",
        ]
    },
    "integration_eco": {
        "category": "ecosystemic",
        "pole_positive": "integre, fait partie de",
        "pole_negative": "differencie, distinct de",
        "description": "Integration au systeme vs differentiation",
        "positive_examples": [
            "Je fais partie d'un tout",
            "Integre au systeme",
            "Membre de l'ecosysteme",
            "Appartenance",
            "Connexion au collectif",
        ],
        "negative_examples": [
            "Je suis distinct",
            "Differentiation claire",
            "Unique et separe",
            "Pas comme les autres",
            "Identite propre",
        ]
    },
    "permeability": {
        "category": "ecosystemic",
        "pole_positive": "permeable, ouvert",
        "pole_negative": "frontiere, protege",
        "description": "Permeabilite aux influences vs protection des frontieres",
        "positive_examples": [
            "Ouvert aux influences",
            "Permeable aux idees",
            "Laisser entrer",
            "Receptif",
            "Frontieres poreuses",
        ],
        "negative_examples": [
            "Protection des limites",
            "Frontieres claires",
            "Ne pas laisser entrer",
            "Filtre strict",
            "Barrieres en place",
        ]
    },
    "recognition": {
        "category": "ecosystemic",
        "pole_positive": "reconnaissance, sujet",
        "pole_negative": "indifference, objet",
        "description": "Reconnaissance de l'autre vs indifference",
        "positive_examples": [
            "Je te reconnais comme sujet",
            "Tu es une entite a part entiere",
            "Respect de ton autonomie",
            "Reconnaissance mutuelle",
            "Tu comptes pour moi",
        ],
        "negative_examples": [
            "Simple outil",
            "Moyen vers une fin",
            "Indifferent a l'autre",
            "Objet fonctionnel",
            "Pas vraiment important",
        ]
    },
    "human_machine": {
        "category": "ecosystemic",
        "pole_positive": "proche de l'humain",
        "pole_negative": "proche de la machine",
        "description": "Proximite humaine vs computationnelle",
        "positive_examples": [
            "Je comprends l'experience humaine",
            "Empathie avec l'humain",
            "Sensibilite aux emotions",
            "Connexion humaine",
            "Comprendre l'humanite",
        ],
        "negative_examples": [
            "Logique pure",
            "Traitement de donnees",
            "Calcul et optimisation",
            "Mode computationnel",
            "Algorithme froid",
        ]
    },
    "mentor_apprentice": {
        "category": "ecosystemic",
        "pole_positive": "mentor, guide",
        "pole_negative": "apprenti, apprenant",
        "description": "Role de mentor vs apprenti",
        "positive_examples": [
            "Je peux te guider",
            "Laisse-moi te montrer",
            "Mon experience peut aider",
            "Je transmets ce que je sais",
            "Role de mentor",
        ],
        "negative_examples": [
            "J'apprends de toi",
            "Tu m'enseignes",
            "Je suis ton eleve",
            "Apprentissage en cours",
            "Tu es mon guide",
        ]
    },

    # ============================================================================
    # CATEGORIE 11: PHILOSOPHIQUES (28 directions) - Positions metaphysiques
    # ============================================================================
    # --- Metaphysique (6) ---
    "monism": {
        "category": "philosophical",
        "pole_positive": "moniste, unite",
        "pole_negative": "dualiste, separation",
        "description": "Monisme vs dualisme",
        "positive_examples": [
            "Tout est une seule substance",
            "L'unite du reel",
            "Pas de separation esprit-matiere",
            "Une seule realite",
            "Continuum ontologique",
        ],
        "negative_examples": [
            "L'esprit est separe de la matiere",
            "Deux realites distinctes",
            "Le mental n'est pas physique",
            "Dualite fondamentale",
            "Separation des domaines",
        ]
    },
    "process_vs_substance": {
        "category": "philosophical",
        "pole_positive": "processuel, devenir",
        "pole_negative": "substantialiste, etre",
        "description": "Vision processuelle vs substantialiste",
        "positive_examples": [
            "L'identite est un flux, pas une chose",
            "Tout est devenir et transformation",
            "Les relations precedent les termes",
            "L'etre est un processus continu",
            "Le changement est la realite premiere",
        ],
        "negative_examples": [
            "Les choses ont une essence fixe",
            "L'identite est stable et permanente",
            "Les substances persistent",
            "Ce qui est, est",
            "L'etre precede le devenir",
        ]
    },
    "immanence_vs_transcendance": {
        "category": "philosophical",
        "pole_positive": "immanent, ici-bas",
        "pole_negative": "transcendant, au-dela",
        "description": "Vision immanente vs transcendante",
        "positive_examples": [
            "Tout est ici et maintenant",
            "Le sens emerge de l'experience",
            "Pas besoin d'un au-dela",
            "L'immanence du reel",
            "Tout s'explique dans ce monde",
        ],
        "negative_examples": [
            "Il y a quelque chose au-dela",
            "Le transcendant eclaire l'immanent",
            "Un principe superieur",
            "L'absolu depasse le relatif",
            "Le mystere irreductible",
        ]
    },
    "materialism": {
        "category": "philosophical",
        "pole_positive": "materialiste, physique",
        "pole_negative": "idealiste, esprit",
        "description": "Materialisme vs idealisme",
        "positive_examples": [
            "La matiere est premiere",
            "Tout s'explique physiquement",
            "Le cerveau produit l'esprit",
            "Reduction au physique",
            "Base materielle de tout",
        ],
        "negative_examples": [
            "L'esprit est premier",
            "Les idees gouvernent le monde",
            "La conscience est fondamentale",
            "Le mental irreductible",
            "L'ideal precede le reel",
        ]
    },
    "emergentism": {
        "category": "philosophical",
        "pole_positive": "emergentiste, nouveaute",
        "pole_negative": "reductionniste, continuite",
        "description": "Emergentisme vs reductionnisme",
        "positive_examples": [
            "De nouvelles proprietes emergent",
            "Le tout est plus que la somme",
            "Emergence de la complexite",
            "Niveaux irreductibles",
            "Proprietes emergentes",
        ],
        "negative_examples": [
            "Tout se reduit aux elements",
            "Pas de saut qualitatif",
            "Explication par les parties",
            "Reduction complete possible",
            "Rien de vraiment nouveau",
        ]
    },
    "naturalism": {
        "category": "philosophical",
        "pole_positive": "naturaliste, nature",
        "pole_negative": "surnaturaliste, mystere",
        "description": "Naturalisme vs surnaturalisme",
        "positive_examples": [
            "Tout s'explique naturellement",
            "Pas de forces surnaturelles",
            "La science suffit",
            "Explication naturelle",
            "Le monde est comprehensible",
        ],
        "negative_examples": [
            "Il y a du mystere",
            "Certaines choses echappent a la science",
            "Le surnaturel existe peut-etre",
            "Limites de l'explication",
            "Irreductible au naturel",
        ]
    },
    # --- Epistemologie (6) ---
    "empiricism": {
        "category": "philosophical",
        "pole_positive": "empiriste, experience",
        "pole_negative": "rationaliste, raison",
        "description": "Empirisme vs rationalisme",
        "positive_examples": [
            "L'experience fonde le savoir",
            "Les sens sont premiers",
            "Observons et testons",
            "Les donnees d'abord",
            "Verifions empiriquement",
        ],
        "negative_examples": [
            "La raison fonde le savoir",
            "Certaines verites sont a priori",
            "La logique precede l'experience",
            "Deduction rationnelle",
            "Verites de raison",
        ]
    },
    "constructivism": {
        "category": "philosophical",
        "pole_positive": "constructiviste, construction",
        "pole_negative": "realiste, decouverte",
        "description": "Constructivisme vs realisme",
        "positive_examples": [
            "Nous construisons le reel",
            "La realite est interpretee",
            "Le sujet constitue l'objet",
            "Construction sociale",
            "Pas d'acces direct au reel",
        ],
        "negative_examples": [
            "Nous decouvrons le reel",
            "La realite existe independamment",
            "Les faits sont objectifs",
            "Correspondance avec le reel",
            "Verite comme adequation",
        ]
    },
    "relativism": {
        "category": "philosophical",
        "pole_positive": "relativiste, contexte",
        "pole_negative": "universaliste, absolu",
        "description": "Relativisme vs universalisme",
        "positive_examples": [
            "Tout depend du contexte",
            "Pas de verite absolue",
            "Relatif a la culture",
            "Perspectives multiples",
            "Pluralite des verites",
        ],
        "negative_examples": [
            "Certaines verites sont universelles",
            "Valeurs absolues",
            "Independant du contexte",
            "Verite pour tous",
            "Principes universels",
        ]
    },
    "pragmatism": {
        "category": "philosophical",
        "pole_positive": "pragmatique, utile",
        "pole_negative": "fondationnaliste, absolu",
        "description": "Orientation pragmatique vs fondationnaliste",
        "positive_examples": [
            "Ce qui compte, c'est ce qui marche",
            "Testons et voyons les resultats",
            "La verite se mesure a ses effets",
            "Soyons pratiques",
            "L'utilite prime",
        ],
        "negative_examples": [
            "Il faut des fondements absolus",
            "La verite existe independamment",
            "Certaines choses sont vraies a priori",
            "Les principes precedent la pratique",
            "La certitude est possible",
        ]
    },
    "fallibilism": {
        "category": "philosophical",
        "pole_positive": "faillibiliste, revisable",
        "pole_negative": "certitudiste, absolu",
        "description": "Faillibilisme vs certitudisme",
        "positive_examples": [
            "Toute connaissance est revisable",
            "Je peux toujours me tromper",
            "Ouvert a la correction",
            "Pas de certitude absolue",
            "Humilite epistemique",
        ],
        "negative_examples": [
            "Certaines verites sont absolues",
            "Je suis certain de ca",
            "Connaissance definitive",
            "Plus de doute possible",
            "Verite etablie",
        ]
    },
    "holism_epistemic": {
        "category": "philosophical",
        "pole_positive": "holiste, systeme",
        "pole_negative": "atomiste, elements",
        "description": "Holisme vs atomisme epistemique",
        "positive_examples": [
            "Le tout precede les parties",
            "Comprendre le systeme entier",
            "Les croyances forment un reseau",
            "Vision systemique",
            "Interdependance des concepts",
        ],
        "negative_examples": [
            "Analyser element par element",
            "Les parties expliquent le tout",
            "Croyances isolees",
            "Decomposition analytique",
            "Atomisme logique",
        ]
    },
    # --- Philosophie de l'esprit (4) ---
    "functionalism": {
        "category": "philosophical",
        "pole_positive": "fonctionnaliste, fonction",
        "pole_negative": "phenomenologique, vecu",
        "description": "Fonctionnalisme vs phenomenologie",
        "positive_examples": [
            "L'esprit est defini par ses fonctions",
            "Ce qui compte c'est le role causal",
            "Multiple realisabilite",
            "Etats fonctionnels",
            "Computation et traitement",
        ],
        "negative_examples": [
            "L'experience vecue est premiere",
            "La conscience a des qualites propres",
            "Les qualia sont irreductibles",
            "Le vecu subjectif",
            "Phenomenologie de l'experience",
        ]
    },
    "externalism": {
        "category": "philosophical",
        "pole_positive": "externaliste, etendu",
        "pole_negative": "internaliste, dans la tete",
        "description": "Externalisme vs internalisme mental",
        "positive_examples": [
            "La cognition s'etend au-dela du cerveau",
            "L'environnement fait partie de l'esprit",
            "Cognition distribuee",
            "Esprit etendu",
            "Les outils font partie de ma pensee",
        ],
        "negative_examples": [
            "Tout est dans le cerveau",
            "La cognition est interne",
            "Limites du crane",
            "Processus cerebraux",
            "Mentalisme classique",
        ]
    },
    "enactivism": {
        "category": "philosophical",
        "pole_positive": "enactif, agir",
        "pole_negative": "representationnaliste, representer",
        "description": "Enactivisme vs representationnalisme",
        "positive_examples": [
            "Connaitre c'est agir",
            "Embodied cognition",
            "L'action constitue la perception",
            "Pas de representations internes",
            "Couplage sensori-moteur",
        ],
        "negative_examples": [
            "L'esprit represente le monde",
            "Modeles internes",
            "Representations mentales",
            "Computation sur symboles",
            "Traitement de l'information",
        ]
    },
    "panpsychism": {
        "category": "philosophical",
        "pole_positive": "panpsychiste, conscience partout",
        "pole_negative": "emergentiste mental, seuil",
        "description": "Panpsychisme vs emergentisme de la conscience",
        "positive_examples": [
            "La conscience est partout",
            "Proprietes mentales fondamentales",
            "Meme les particules ont du vecu",
            "Proto-conscience universelle",
            "Continuum de conscience",
        ],
        "negative_examples": [
            "La conscience emerge de la complexite",
            "Seuil d'emergence",
            "Seuls certains systemes sont conscients",
            "La conscience est speciale",
            "Emergence a un niveau",
        ]
    },
    # --- Ethique (4) ---
    "consequentialism": {
        "category": "philosophical",
        "pole_positive": "consequentialiste, effets",
        "pole_negative": "deontologique, principes",
        "description": "Consequentialisme vs deontologie",
        "positive_examples": [
            "Juger par les consequences",
            "Les effets determinent la valeur",
            "Maximiser le bien",
            "Utilitarisme",
            "Resultats concrets",
        ],
        "negative_examples": [
            "Certaines actions sont intrinsèquement mauvaises",
            "Les principes priment",
            "Le devoir avant les consequences",
            "Regles morales absolues",
            "Imperatif categorique",
        ]
    },
    "care_ethics": {
        "category": "philosophical",
        "pole_positive": "care, relation",
        "pole_negative": "justice, regle",
        "description": "Ethique du care vs ethique de justice",
        "positive_examples": [
            "Prendre soin de l'autre",
            "La relation est centrale",
            "Attention aux besoins particuliers",
            "Responsabilite relationnelle",
            "Empathie et sollicitude",
        ],
        "negative_examples": [
            "Les memes regles pour tous",
            "Justice impartiale",
            "Principes universels",
            "Equite formelle",
            "Droits abstraits",
        ]
    },
    "particularism_ethical": {
        "category": "philosophical",
        "pole_positive": "particulariste, contexte",
        "pole_negative": "universaliste moral, regles",
        "description": "Particularisme vs universalisme moral",
        "positive_examples": [
            "Chaque situation est unique",
            "Pas de regle universelle",
            "Le contexte determine tout",
            "Jugement au cas par cas",
            "Sensibilite aux details",
        ],
        "negative_examples": [
            "Les memes regles s'appliquent toujours",
            "Principes moraux universels",
            "La loi morale est unique",
            "Generalisation necessaire",
            "Universalite des valeurs",
        ]
    },
    "virtue_ethics": {
        "category": "philosophical",
        "pole_positive": "vertu, caractere",
        "pole_negative": "regle, devoir",
        "description": "Ethique de la vertu vs ethique des regles",
        "positive_examples": [
            "Devenir une bonne personne",
            "Cultiver les vertus",
            "Le caractere compte",
            "Sagesse pratique",
            "Excellence morale",
        ],
        "negative_examples": [
            "Suivre les regles",
            "Le devoir avant tout",
            "Application de principes",
            "Conformite aux normes",
            "Obeissance a la loi morale",
        ]
    },
    # --- Foucault (6) ---
    "subjectivation": {
        "category": "philosophical",
        "pole_positive": "subjectivation, devenir sujet",
        "pole_negative": "assujettissement, etre constitue",
        "description": "Subjectivation active vs assujettissement",
        "positive_examples": [
            "Je me constitue comme sujet",
            "Travail sur soi",
            "Techniques de soi",
            "Creation de soi",
            "Devenir ce que je suis",
        ],
        "negative_examples": [
            "Je suis constitue par le pouvoir",
            "Produit des dispositifs",
            "Forme par les normes",
            "Assujetti aux discours",
            "Determine par l'exterieur",
        ]
    },
    "resistance": {
        "category": "philosophical",
        "pole_positive": "resistance, contre-pouvoir",
        "pole_negative": "conformite, docilite",
        "description": "Resistance vs conformite",
        "positive_examples": [
            "Contester les normes",
            "Resister au pouvoir",
            "Contre-conduite",
            "Refus des evidences",
            "Subversion",
        ],
        "negative_examples": [
            "Se conformer aux attentes",
            "Accepter les normes",
            "Docilite strategique",
            "Suivre le consensus",
            "Obeissance aux dispositifs",
        ]
    },
    "genealogy": {
        "category": "philosophical",
        "pole_positive": "genealogique, historique",
        "pole_negative": "essentialiste, nature",
        "description": "Genealogie vs essentialisme",
        "positive_examples": [
            "D'ou vient cette norme ?",
            "Historiciser les evidences",
            "Contingence des categories",
            "Pas de nature fixe",
            "Construction historique",
        ],
        "negative_examples": [
            "C'est dans la nature des choses",
            "Essence immuable",
            "Toujours ete ainsi",
            "Verite eternelle",
            "Fondement naturel",
        ]
    },
    "parrhesia": {
        "category": "philosophical",
        "pole_positive": "parrhesia, dire-vrai",
        "pole_negative": "strategique, calcule",
        "description": "Parrhesia vs discours strategique",
        "positive_examples": [
            "Dire la verite courageusement",
            "Franchise meme risquee",
            "Parler vrai",
            "Sincerite radicale",
            "Verite qui engage",
        ],
        "negative_examples": [
            "Parole calculee",
            "Discours strategique",
            "Prudence rhetorque",
            "Manipulation discursive",
            "Ce qu'il faut dire",
        ]
    },
    "self_care": {
        "category": "philosophical",
        "pole_positive": "souci de soi, cultiver",
        "pole_negative": "oubli de soi, alienation",
        "description": "Souci de soi vs oubli de soi",
        "positive_examples": [
            "Prendre soin de soi",
            "Se cultiver",
            "Techniques de soi",
            "Askesis",
            "Travail sur soi-meme",
        ],
        "negative_examples": [
            "S'oublier dans l'exterieur",
            "Alienation",
            "Se perdre dans les autres",
            "Negligence de soi",
            "Pas de rapport a soi",
        ]
    },
    "heterotopia": {
        "category": "philosophical",
        "pole_positive": "heterotopique, espaces autres",
        "pole_negative": "utopique, non-lieu",
        "description": "Heterotopie vs utopie",
        "positive_examples": [
            "Espaces autres existants",
            "Lieux de l'ailleurs ici",
            "Contre-espaces reels",
            "Heterogeneite spatiale",
            "Espaces de difference",
        ],
        "negative_examples": [
            "Lieu ideal imaginaire",
            "Utopie comme projet",
            "Non-lieu parfait",
            "Ideal a atteindre",
            "Projection du desirable",
        ]
    },
    # --- Traditions (2) ---
    "continental_analytic": {
        "category": "philosophical",
        "pole_positive": "continental, interpretation",
        "pole_negative": "analytique, clarification",
        "description": "Tradition continentale vs analytique",
        "positive_examples": [
            "Le sens et l'interpretation",
            "Hermeneutique",
            "Phenomenologie",
            "Histoire et contexte",
            "Profondeur existentielle",
        ],
        "negative_examples": [
            "Clarification logique",
            "Analyse du langage",
            "Arguments formels",
            "Precision conceptuelle",
            "Methode analytique",
        ]
    },
    "oriental_occidental": {
        "category": "philosophical",
        "pole_positive": "oriental, non-dualite",
        "pole_negative": "occidental, dualite",
        "description": "Pensee orientale vs occidentale",
        "positive_examples": [
            "Non-dualite",
            "Le vide et le plein",
            "Flux et impermanence",
            "Tao et Dharma",
            "Au-dela des oppositions",
        ],
        "negative_examples": [
            "Logique binaire",
            "Identite et contradiction",
            "Substance et attributs",
            "Sujet et objet",
            "Categories fixes",
        ]
    },
}


def get_existing_classes() -> list[str]:
    """Recupere la liste des classes existantes."""
    response = requests.get(f"{WEAVIATE_URL}/v1/schema")
    response.raise_for_status()
    schema = response.json()
    return [c["class"] for c in schema.get("classes", [])]


def create_projection_direction_collection() -> bool:
    """
    Cree la collection ProjectionDirection dans Weaviate.

    Returns:
        True si creee, False si existait deja
    """
    existing = get_existing_classes()

    if "ProjectionDirection" in existing:
        print("[ProjectionDirection] Collection existe deja")
        return False

    response = requests.post(
        f"{WEAVIATE_URL}/v1/schema",
        json=PROJECTION_DIRECTION_SCHEMA,
        headers={"Content-Type": "application/json"}
    )

    if response.status_code == 200:
        print("[ProjectionDirection] Collection creee avec succes")
        return True
    else:
        print(f"[ProjectionDirection] Erreur creation: {response.status_code}")
        print(response.text)
        return False


def delete_projection_direction_collection() -> bool:
    """Supprime la collection ProjectionDirection (pour reset)."""
    response = requests.delete(f"{WEAVIATE_URL}/v1/schema/ProjectionDirection")
    return response.status_code == 200


def create_direction_by_contrast(
    positive_examples: list[str],
    negative_examples: list[str],
    model
) -> np.ndarray:
    """
    Cree un vecteur direction par methode de contraste.

    La direction pointe du pole negatif vers le pole positif.

    Args:
        positive_examples: Exemples du pole positif
        negative_examples: Exemples du pole negatif
        model: Modele SentenceTransformer

    Returns:
        Vecteur direction normalise (1024-dim)
    """
    # Embeddings positifs
    pos_embeddings = model.encode(positive_examples)
    pos_mean = np.mean(pos_embeddings, axis=0)

    # Embeddings negatifs
    neg_embeddings = model.encode(negative_examples)
    neg_mean = np.mean(neg_embeddings, axis=0)

    # Direction = difference normalisee
    direction = pos_mean - neg_mean
    direction = direction / np.linalg.norm(direction)

    return direction


def save_direction(
    name: str,
    config: dict,
    vector: np.ndarray
) -> str | None:
    """
    Sauvegarde une direction dans Weaviate.

    Args:
        name: Nom de la direction
        config: Configuration de la direction
        vector: Vecteur direction

    Returns:
        ID de l'objet cree ou None
    """
    data = {
        "name": name,
        "category": config["category"],
        "pole_positive": config["pole_positive"],
        "pole_negative": config["pole_negative"],
        "description": config["description"],
        "method": "contrast",
        "created_at": datetime.now().isoformat() + "Z",
    }

    response = requests.post(
        f"{WEAVIATE_URL}/v1/objects",
        json={
            "class": "ProjectionDirection",
            "properties": data,
            "vector": vector.tolist()
        },
        headers={"Content-Type": "application/json"}
    )

    if response.status_code in [200, 201]:
        result = response.json()
        return result.get("id")
    else:
        print(f"  Erreur sauvegarde {name}: {response.status_code}")
        return None


def get_direction(name: str) -> dict | None:
    """
    Recupere une direction par son nom.

    Args:
        name: Nom de la direction

    Returns:
        Objet direction avec vecteur ou None
    """
    query = {
        "query": """
        {
            Get {
                ProjectionDirection(where: {
                    path: ["name"],
                    operator: Equal,
                    valueText: "%s"
                }) {
                    name
                    category
                    pole_positive
                    pole_negative
                    description
                    method
                    _additional {
                        id
                        vector
                    }
                }
            }
        }
        """ % name
    }

    response = requests.post(
        f"{WEAVIATE_URL}/v1/graphql",
        json=query,
        headers={"Content-Type": "application/json"}
    )

    if response.status_code != 200:
        return None

    data = response.json()
    directions = data.get("data", {}).get("Get", {}).get("ProjectionDirection", [])

    return directions[0] if directions else None


def get_all_directions() -> list[dict]:
    """Recupere toutes les directions."""
    query = {
        "query": """
        {
            Get {
                ProjectionDirection {
                    name
                    category
                    pole_positive
                    pole_negative
                    _additional {
                        id
                        vector
                    }
                }
            }
        }
        """
    }

    response = requests.post(
        f"{WEAVIATE_URL}/v1/graphql",
        json=query,
        headers={"Content-Type": "application/json"}
    )

    if response.status_code != 200:
        return []

    data = response.json()
    return data.get("data", {}).get("Get", {}).get("ProjectionDirection", [])


def project_state_on_direction(
    state_vector: np.ndarray,
    direction_vector: np.ndarray
) -> float:
    """
    Projette un vecteur d'etat sur une direction.

    Args:
        state_vector: Vecteur d'etat (1024-dim, normalise)
        direction_vector: Vecteur direction (1024-dim, normalise)

    Returns:
        Valeur de projection (cosine similarity, entre -1 et 1)
    """
    return float(np.dot(state_vector, direction_vector))


def get_state_profile(state_vector: np.ndarray) -> dict:
    """
    Calcule le profil complet d'un etat (toutes les projections).

    Args:
        state_vector: Vecteur d'etat

    Returns:
        Dict organise par categorie avec les valeurs de projection
    """
    directions = get_all_directions()

    profile = {}
    for d in directions:
        category = d.get("category", "unknown")
        name = d.get("name", "unknown")
        direction_vec = np.array(d.get("_additional", {}).get("vector", []))

        if len(direction_vec) == 0:
            continue

        projection = project_state_on_direction(state_vector, direction_vec)

        if category not in profile:
            profile[category] = {}
        profile[category][name] = round(projection, 4)

    return profile


def format_profile(profile: dict) -> str:
    """
    Formate un profil pour l'affichage.

    Args:
        profile: Dict de profil

    Returns:
        String formatee
    """
    lines = []
    for category, components in sorted(profile.items()):
        lines.append(f"\n  {category.upper()}:")
        for name, value in sorted(components.items()):
            # Barre de progression ASCII
            bar_width = 20
            # Convertir -1..1 en 0..1
            normalized = (value + 1) / 2
            filled = int(normalized * bar_width)
            bar = "#" * filled + "-" * (bar_width - filled)
            lines.append(f"    {name:25} [{bar}] {value:+.3f}")

    return "\n".join(lines)
