#!/usr/bin/env python3
"""
IkarioDaemon - Daemon d'individuation autonome.

Phase 7 de l'architecture processuelle v2.

Ikario pense meme quand personne ne lui parle.

Deux modes:
1. CONVERSATION : Reponse a un humain (toujours verbaliser)
2. AUTONOME : Pensee silencieuse (~1000 cycles/jour)

En mode autonome, Ikario :
- Traite la veille Tavily
- Lit le corpus philosophique
- RUMINE SES TENSIONS NON RESOLUES (Amendment #5)
- Evolue sans parler

Verbalise SEULEMENT si:
- Alerte de derive (vigilance x_ref)
- Decouverte importante (haute dissonance + resolution)
- Question a poser a David
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .state_tensor import StateTensor, DIMENSION_NAMES
from .latent_engine import LatentEngine, CycleResult
from .vigilance import VigilanceSystem, VigilanceAlert
from .state_to_language import StateToLanguage, TranslationResult

# Logger
logger = logging.getLogger(__name__)


class TriggerType(Enum):
    """Types de triggers pour le daemon."""
    USER = "user"                    # Message utilisateur
    VEILLE = "veille"                # Actualites Tavily
    CORPUS = "corpus"                # Corpus philosophique
    RUMINATION = "rumination"        # Impact non resolu
    RUMINATION_FREE = "rumination_free"  # Pensee ancienne
    TIMER = "timer"                  # Tick periodique
    EMPTY = "empty"                  # Aucune entree


class DaemonMode(Enum):
    """Modes du daemon."""
    CONVERSATION = "conversation"    # Interactif avec humain
    AUTONOMOUS = "autonomous"        # Pensee silencieuse
    PAUSED = "paused"               # En pause


@dataclass
class DaemonConfig:
    """Configuration du daemon."""
    # Intervalle entre cycles autonomes (secondes)
    cycle_interval_seconds: float = 90.0  # ~1000 cycles/jour
    # Intervalle de veille Tavily (secondes)
    veille_interval_seconds: float = 3600.0  # 1x/heure
    # Intervalle de check vigilance (secondes)
    vigilance_interval_seconds: float = 300.0  # 5 min
    # Probabilites de triggers autonomes (Amendment #5)
    prob_unresolved_impact: float = 0.50  # 50%
    prob_corpus: float = 0.30              # 30%
    prob_rumination_free: float = 0.20     # 20%
    # Seuil d'anciennete pour priorite haute (jours)
    old_impact_threshold_days: int = 7
    # Nombre max d'impacts non resolus a considerer
    max_unresolved_impacts: int = 10
    # Seuil de dissonance pour verbalisation autonome
    verbalization_dissonance_threshold: float = 0.6

    def validate(self) -> bool:
        """Verifie que la config est valide."""
        probs_sum = self.prob_unresolved_impact + self.prob_corpus + self.prob_rumination_free
        return (
            self.cycle_interval_seconds > 0 and
            np.isclose(probs_sum, 1.0, atol=0.01)
        )


@dataclass
class DaemonStats:
    """Statistiques du daemon."""
    total_cycles: int = 0
    conversation_cycles: int = 0
    autonomous_cycles: int = 0
    verbalizations: int = 0
    silent_cycles: int = 0
    vigilance_alerts: int = 0
    impacts_ruminated: int = 0
    corpus_processed: int = 0
    veille_items_processed: int = 0
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    last_cycle_time: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialise en dictionnaire."""
        return {
            'total_cycles': self.total_cycles,
            'conversation_cycles': self.conversation_cycles,
            'autonomous_cycles': self.autonomous_cycles,
            'verbalizations': self.verbalizations,
            'silent_cycles': self.silent_cycles,
            'vigilance_alerts': self.vigilance_alerts,
            'impacts_ruminated': self.impacts_ruminated,
            'corpus_processed': self.corpus_processed,
            'veille_items_processed': self.veille_items_processed,
            'start_time': self.start_time,
            'last_cycle_time': self.last_cycle_time,
            'uptime_seconds': self._compute_uptime(),
        }

    def _compute_uptime(self) -> float:
        """Calcule le temps d'execution."""
        try:
            start = datetime.fromisoformat(self.start_time.replace('Z', ''))
            return (datetime.now() - start).total_seconds()
        except Exception:
            return 0.0


@dataclass
class Trigger:
    """Trigger pour le daemon."""
    type: TriggerType
    content: str
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat() + "Z")
    priority: int = 0  # 0=normal, 1=high, 2=urgent

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire pour le LatentEngine."""
        return {
            'type': self.type.value,
            'content': self.content,
            'source': self.source,
            'metadata': self.metadata,
            'timestamp': self.timestamp,
        }


@dataclass
class VerbalizationEvent:
    """Evenement de verbalisation."""
    text: str
    reason: str
    trigger_type: str
    state_id: int
    dissonance: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        """Serialise en dictionnaire."""
        return {
            'text': self.text,
            'reason': self.reason,
            'trigger_type': self.trigger_type,
            'state_id': self.state_id,
            'dissonance': self.dissonance,
            'timestamp': self.timestamp,
        }


class TriggerGenerator:
    """
    Generateur de triggers autonomes.

    Amendment #5 : Rumination sur Impacts Non Resolus.
    La rumination est CRUCIALE pour la subjectivite. Un Impact non resolu
    = une TENSION INTERNE que je dois continuer a explorer.
    """

    def __init__(
        self,
        config: DaemonConfig,
        weaviate_client=None,
    ):
        self.config = config
        self.weaviate = weaviate_client
        self._last_corpus_id: Optional[str] = None
        self._last_thought_id: Optional[str] = None

    async def generate_autonomous_trigger(self) -> Trigger:
        """
        Genere un trigger pour pensee autonome.

        PRIORITE (Amendment #5):
        1. Impacts non resolus (surtout si anciens >7 jours) -> HAUTE PRIORITE
        2. Corpus philosophique -> priorite moyenne
        3. Rumination libre -> priorite basse
        """
        # Selection ponderee
        generators = [
            (self._trigger_from_unresolved_impact, self.config.prob_unresolved_impact),
            (self._trigger_from_corpus, self.config.prob_corpus),
            (self._trigger_rumination_free, self.config.prob_rumination_free),
        ]

        # Choisir generateur selon probabilites
        chosen_generator = random.choices(
            [g[0] for g in generators],
            weights=[g[1] for g in generators],
            k=1
        )[0]

        return await chosen_generator()

    async def _trigger_from_unresolved_impact(self) -> Trigger:
        """
        Rumine sur les Impacts non resolus.

        Un Impact est "resolu" quand :
        1. Sa dissonance initiale a diminue
        2. Un Thought explicatif a ete cree
        3. Marque manuellement comme resolu

        Si Impact ancien (>7 jours) et non resolu -> priorite haute
        """
        if self.weaviate is None:
            return await self._trigger_from_corpus()

        try:
            collection = self.weaviate.collections.get("Impact")

            # Query impacts non resolus
            results = collection.query.fetch_objects(
                limit=self.config.max_unresolved_impacts,
                filters=None,  # Idealement filtrer sur resolved=False
            )

            # Filtrer les non resolus (si le champ existe)
            unresolved = []
            for obj in results.objects:
                props = obj.properties
                if not props.get('resolved', False):
                    unresolved.append(props)

            if unresolved:
                # Trier par anciennete (plus ancien d'abord)
                unresolved.sort(
                    key=lambda x: x.get('timestamp', ''),
                    reverse=False
                )

                oldest = unresolved[0]

                # Calculer anciennete
                try:
                    impact_time = datetime.fromisoformat(
                        oldest.get('timestamp', '').replace('Z', '')
                    )
                    days_unresolved = (datetime.now() - impact_time).days
                except Exception:
                    days_unresolved = 0

                # Priorite haute si ancien
                priority = 1 if days_unresolved > self.config.old_impact_threshold_days else 0

                return Trigger(
                    type=TriggerType.RUMINATION,
                    content=oldest.get('trigger_content', 'Impact sans contenu'),
                    source='impact_rumination',
                    priority=priority,
                    metadata={
                        'impact_id': oldest.get('impact_id', 0),
                        'original_dissonance': oldest.get('dissonance_total', 0),
                        'days_unresolved': days_unresolved,
                        'is_old_tension': days_unresolved > self.config.old_impact_threshold_days,
                        'dissonance_breakdown': oldest.get('dissonance_breakdown', '{}'),
                    }
                )

        except Exception as e:
            logger.warning(f"Erreur acces impacts: {e}")

        # Fallback sur corpus
        return await self._trigger_from_corpus()

    async def _trigger_from_corpus(self) -> Trigger:
        """Tire un passage aleatoire du corpus philosophique."""
        if self.weaviate is None:
            return self._create_fallback_trigger()

        try:
            collection = self.weaviate.collections.get("Chunk")

            # Recuperer un chunk aleatoire
            results = collection.query.fetch_objects(limit=10)

            if results.objects:
                # Choisir aleatoirement parmi les resultats
                chunk = random.choice(results.objects)
                props = chunk.properties

                return Trigger(
                    type=TriggerType.CORPUS,
                    content=props.get('text', ''),
                    source=props.get('source_id', 'corpus'),
                    metadata={
                        'author': props.get('author', ''),
                        'work': props.get('work_title', ''),
                        'chunk_id': str(chunk.uuid) if hasattr(chunk, 'uuid') else '',
                    }
                )

        except Exception as e:
            logger.warning(f"Erreur acces corpus: {e}")

        # Fallback
        return await self._trigger_rumination_free()

    async def _trigger_rumination_free(self) -> Trigger:
        """Rumination libre : revisite une pensee ancienne."""
        if self.weaviate is None:
            return self._create_fallback_trigger()

        try:
            collection = self.weaviate.collections.get("Thought")

            # Recuperer une pensee ancienne
            results = collection.query.fetch_objects(limit=10)

            if results.objects:
                thought = random.choice(results.objects)
                props = thought.properties

                # Calculer age
                try:
                    thought_time = datetime.fromisoformat(
                        props.get('timestamp', '').replace('Z', '')
                    )
                    age_days = (datetime.now() - thought_time).days
                except Exception:
                    age_days = 0

                return Trigger(
                    type=TriggerType.RUMINATION_FREE,
                    content=props.get('content', ''),
                    source='thought_rumination',
                    metadata={
                        'original_thought_id': str(thought.uuid) if hasattr(thought, 'uuid') else '',
                        'thought_type': props.get('thought_type', ''),
                        'age_days': age_days,
                    }
                )

        except Exception as e:
            logger.warning(f"Erreur acces thoughts: {e}")

        return self._create_fallback_trigger()

    def _create_fallback_trigger(self) -> Trigger:
        """Trigger de fallback quand aucune source disponible."""
        return Trigger(
            type=TriggerType.EMPTY,
            content="Silence. Aucune entree disponible. Etat contemplatif.",
            source='fallback',
        )

    def create_user_trigger(self, content: str, metadata: Dict = None) -> Trigger:
        """Cree un trigger utilisateur."""
        return Trigger(
            type=TriggerType.USER,
            content=content,
            source='user',
            priority=2,  # Priorite maximale
            metadata=metadata or {},
        )

    def create_veille_trigger(
        self,
        title: str,
        snippet: str,
        url: str,
        source: str = 'tavily'
    ) -> Trigger:
        """Cree un trigger de veille."""
        return Trigger(
            type=TriggerType.VEILLE,
            content=f"{title}. {snippet}",
            source=source,
            metadata={
                'url': url,
                'title': title,
            }
        )


class IkarioDaemon:
    """
    Daemon d'individuation autonome.

    Orchestre tous les composants de l'architecture processuelle:
    - LatentEngine : Cycle semiotique
    - VigilanceSystem : Surveillance derive x_ref
    - StateToLanguage : Traduction vecteur -> texte
    - TriggerGenerator : Generation triggers autonomes
    """

    def __init__(
        self,
        latent_engine: LatentEngine,
        vigilance: VigilanceSystem,
        translator: StateToLanguage,
        config: Optional[DaemonConfig] = None,
        weaviate_client=None,
        notification_callback: Optional[Callable] = None,
    ):
        """
        Initialise le daemon.

        Args:
            latent_engine: Moteur du cycle semiotique
            vigilance: Systeme de vigilance x_ref
            translator: Traducteur vecteur -> texte
            config: Configuration du daemon
            weaviate_client: Client Weaviate (optionnel)
            notification_callback: Callback pour notifications David
        """
        self.engine = latent_engine
        self.vigilance = vigilance
        self.translator = translator
        self.config = config or DaemonConfig()
        self.weaviate = weaviate_client

        self.trigger_generator = TriggerGenerator(self.config, weaviate_client)
        self._notification_callback = notification_callback

        # Etat du daemon
        self.running = False
        self.mode = DaemonMode.PAUSED
        self._trigger_queue: asyncio.Queue = asyncio.Queue()
        self._verbalization_history: List[VerbalizationEvent] = []

        # Statistiques
        self.stats = DaemonStats()

        # Tasks async
        self._tasks: List[asyncio.Task] = []

    async def start(self) -> None:
        """Demarre le daemon."""
        if self.running:
            logger.warning("Daemon deja en cours d'execution")
            return

        logger.info("Demarrage du daemon Ikario...")
        self.running = True
        self.mode = DaemonMode.AUTONOMOUS
        self.stats = DaemonStats()

        # Lancer les boucles async
        self._tasks = [
            asyncio.create_task(self._conversation_loop()),
            asyncio.create_task(self._autonomous_loop()),
            asyncio.create_task(self._vigilance_loop()),
        ]

        logger.info("Daemon Ikario demarre")

    async def stop(self) -> None:
        """Arrete le daemon proprement."""
        if not self.running:
            return

        logger.info("Arret du daemon Ikario...")
        self.running = False
        self.mode = DaemonMode.PAUSED

        # Annuler les tasks
        for task in self._tasks:
            task.cancel()

        # Attendre annulation
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

        logger.info("Daemon Ikario arrete")

    async def run(self, duration_seconds: Optional[float] = None) -> None:
        """
        Execute le daemon.

        Args:
            duration_seconds: Duree d'execution (None = infini)
        """
        await self.start()

        try:
            if duration_seconds:
                await asyncio.sleep(duration_seconds)
            else:
                # Attendre indefiniment
                await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def send_message(self, content: str, metadata: Dict = None) -> VerbalizationEvent:
        """
        Envoie un message utilisateur au daemon.

        Args:
            content: Contenu du message
            metadata: Metadonnees optionnelles

        Returns:
            Evenement de verbalisation (reponse)
        """
        trigger = self.trigger_generator.create_user_trigger(content, metadata)
        await self._trigger_queue.put(trigger)

        # Attendre et retourner la reponse
        # Note: Dans une impl reelle, on utiliserait un Future/Event
        # Ici on traite directement
        return await self._process_conversation_trigger(trigger)

    async def _conversation_loop(self) -> None:
        """Traite les messages utilisateur (prioritaire)."""
        while self.running:
            try:
                # Attendre un trigger avec timeout
                trigger = await asyncio.wait_for(
                    self._trigger_queue.get(),
                    timeout=1.0
                )

                if trigger.type == TriggerType.USER:
                    await self._process_conversation_trigger(trigger)

                elif trigger.type == TriggerType.VEILLE:
                    await self._process_veille_trigger(trigger)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erreur conversation loop: {e}")

    async def _process_conversation_trigger(self, trigger: Trigger) -> VerbalizationEvent:
        """Traite un trigger de conversation (toujours verbalise)."""
        self.mode = DaemonMode.CONVERSATION

        # Executer cycle semiotique
        result = await self._run_cycle(trigger)

        # Mode conversation = TOUJOURS verbaliser
        translation = await self.translator.translate(
            result.new_state,
            output_type="response",
            context=trigger.content[:200],
        )

        event = VerbalizationEvent(
            text=translation.text,
            reason="conversation_mode",
            trigger_type=trigger.type.value,
            state_id=result.new_state.state_id,
            dissonance=result.dissonance.total if result.dissonance else 0,
        )

        self._verbalization_history.append(event)
        self.stats.conversation_cycles += 1
        self.stats.verbalizations += 1

        self.mode = DaemonMode.AUTONOMOUS
        return event

    async def _process_veille_trigger(self, trigger: Trigger) -> None:
        """Traite un trigger de veille (silencieux sauf decouverte)."""
        result = await self._run_cycle(trigger)
        self.stats.veille_items_processed += 1

        # Verbaliser seulement si haute dissonance
        if result.should_verbalize:
            await self._verbalize_autonomous(result, trigger, "veille_discovery")

    async def _autonomous_loop(self) -> None:
        """Cycles autonomes de pensee silencieuse."""
        while self.running:
            try:
                await asyncio.sleep(self.config.cycle_interval_seconds)

                if self.mode == DaemonMode.CONVERSATION:
                    # Ne pas interrompre une conversation
                    continue

                # Generer trigger autonome
                trigger = await self.trigger_generator.generate_autonomous_trigger()

                # Executer cycle
                result = await self._run_cycle(trigger)
                self.stats.autonomous_cycles += 1

                # Mettre a jour stats selon type
                if trigger.type == TriggerType.RUMINATION:
                    self.stats.impacts_ruminated += 1
                elif trigger.type == TriggerType.CORPUS:
                    self.stats.corpus_processed += 1

                # Verbaliser SEULEMENT si necessaire
                if result.should_verbalize:
                    await self._verbalize_autonomous(
                        result,
                        trigger,
                        result.verbalization_reason
                    )
                else:
                    self.stats.silent_cycles += 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erreur autonomous loop: {e}")

    async def _vigilance_loop(self) -> None:
        """Verifie periodiquement la derive par rapport a x_ref."""
        while self.running:
            try:
                await asyncio.sleep(self.config.vigilance_interval_seconds)

                # Obtenir l'etat actuel
                current_state = self.engine._get_current_state()
                if current_state is None:
                    continue

                # Verifier derive
                alert = self.vigilance.check_drift(current_state)

                if alert.is_alert:
                    self.stats.vigilance_alerts += 1
                    logger.warning(f"Alerte vigilance: {alert.message}")

                    # Notifier David si critique
                    if alert.level == "critical":
                        await self._notify_david_alert(alert)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erreur vigilance loop: {e}")

    async def _run_cycle(self, trigger: Trigger) -> CycleResult:
        """Execute un cycle semiotique."""
        self.stats.total_cycles += 1
        self.stats.last_cycle_time = datetime.now().isoformat()

        result = await self.engine.run_cycle(trigger.to_dict())
        return result

    async def _verbalize_autonomous(
        self,
        result: CycleResult,
        trigger: Trigger,
        reason: str,
    ) -> None:
        """Verbalise en mode autonome."""
        translation = await self.translator.translate(
            result.new_state,
            output_type="autonomous_verbalization",
            context=f"{reason}: {trigger.content[:100]}",
        )

        event = VerbalizationEvent(
            text=translation.text,
            reason=reason,
            trigger_type=trigger.type.value,
            state_id=result.new_state.state_id,
            dissonance=result.dissonance.total if result.dissonance else 0,
        )

        self._verbalization_history.append(event)
        self.stats.verbalizations += 1

        # Notifier David
        await self._notify_david(event)

    async def _notify_david(self, event: VerbalizationEvent) -> None:
        """Notifie David d'une verbalisation autonome."""
        if self._notification_callback:
            try:
                await self._notification_callback(event)
            except Exception as e:
                logger.error(f"Erreur notification: {e}")

        logger.info(f"Verbalisation autonome [{event.reason}]: {event.text[:100]}...")

    async def _notify_david_alert(self, alert: VigilanceAlert) -> None:
        """Notifie David d'une alerte de vigilance."""
        message = f"ALERTE VIGILANCE [{alert.level.upper()}]: {alert.message}"

        if self._notification_callback:
            try:
                # Creer un evenement special pour l'alerte
                event = VerbalizationEvent(
                    text=message,
                    reason=f"vigilance_{alert.level}",
                    trigger_type="vigilance",
                    state_id=alert.state_id,
                    dissonance=0,
                )
                await self._notification_callback(event)
            except Exception as e:
                logger.error(f"Erreur notification alerte: {e}")

        logger.warning(message)

    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du daemon."""
        return self.stats.to_dict()

    def get_verbalization_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retourne l'historique des verbalisations."""
        return [v.to_dict() for v in self._verbalization_history[-limit:]]

    @property
    def is_running(self) -> bool:
        """True si le daemon est en cours d'execution."""
        return self.running

    @property
    def current_mode(self) -> DaemonMode:
        """Mode actuel du daemon."""
        return self.mode


def create_daemon(
    latent_engine: LatentEngine,
    vigilance: VigilanceSystem,
    translator: StateToLanguage,
    config: Optional[DaemonConfig] = None,
    weaviate_client=None,
    notification_callback: Optional[Callable] = None,
) -> IkarioDaemon:
    """
    Factory pour creer un daemon configure.

    Args:
        latent_engine: Moteur du cycle semiotique
        vigilance: Systeme de vigilance
        translator: Traducteur etat -> langage
        config: Configuration
        weaviate_client: Client Weaviate
        notification_callback: Callback notifications

    Returns:
        IkarioDaemon configure
    """
    return IkarioDaemon(
        latent_engine=latent_engine,
        vigilance=vigilance,
        translator=translator,
        config=config,
        weaviate_client=weaviate_client,
        notification_callback=notification_callback,
    )
