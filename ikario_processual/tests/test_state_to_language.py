#!/usr/bin/env python3
"""
Tests pour le module state_to_language - Phase 5.

Le cycle de traduction :
1. Projeter StateTensor sur directions interpretables
2. Construire prompt de traduction
3. LLM en mode ZERO-REASONING
4. Valider absence de raisonnement

Executer: pytest ikario_processual/tests/test_state_to_language.py -v
"""

import json
import numpy as np
import pytest
import asyncio

from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ikario_processual.state_tensor import StateTensor, DIMENSION_NAMES, EMBEDDING_DIM
from ikario_processual.state_to_language import (
    ProjectionDirection,
    TranslationResult,
    StateToLanguage,
    REASONING_MARKERS,
    CATEGORY_TO_DIMENSION,
    create_directions_from_config,
)


def create_random_tensor(state_id: int = 0) -> StateTensor:
    """Cree un tenseur avec des vecteurs aleatoires normalises."""
    tensor = StateTensor(
        state_id=state_id,
        timestamp=datetime.now().isoformat(),
    )
    for dim_name in DIMENSION_NAMES:
        v = np.random.randn(EMBEDDING_DIM)
        v = v / np.linalg.norm(v)
        setattr(tensor, dim_name, v)
    return tensor


def create_random_direction(name: str, category: str) -> ProjectionDirection:
    """Cree une direction aleatoire normalisee."""
    v = np.random.randn(EMBEDDING_DIM)
    v = v / np.linalg.norm(v)
    return ProjectionDirection(
        name=name,
        category=category,
        pole_positive="positive",
        pole_negative="negative",
        description=f"Direction {name}",
        vector=v,
    )


class TestProjectionDirection:
    """Tests pour la classe ProjectionDirection."""

    def test_create_direction(self):
        """Creer une direction."""
        v = np.random.randn(EMBEDDING_DIM)
        v = v / np.linalg.norm(v)

        direction = ProjectionDirection(
            name="curiosity",
            category="epistemic",
            pole_positive="curieux",
            pole_negative="desinteresse",
            description="Degre de curiosite",
            vector=v,
        )

        assert direction.name == "curiosity"
        assert direction.category == "epistemic"
        assert direction.vector.shape == (EMBEDDING_DIM,)

    def test_project_on_direction(self):
        """Projection sur une direction."""
        v = np.random.randn(EMBEDDING_DIM)
        v = v / np.linalg.norm(v)

        direction = ProjectionDirection(
            name="test",
            category="test",
            pole_positive="",
            pole_negative="",
            description="",
            vector=v,
        )

        # Projeter le meme vecteur
        projection = direction.project(v)
        assert np.isclose(projection, 1.0)

        # Projeter un vecteur oppose
        projection_neg = direction.project(-v)
        assert np.isclose(projection_neg, -1.0)

    def test_projection_range(self):
        """Les projections sont entre -1 et 1."""
        direction = create_random_direction("test", "test")

        for _ in range(10):
            random_vec = np.random.randn(EMBEDDING_DIM)
            random_vec = random_vec / np.linalg.norm(random_vec)

            projection = direction.project(random_vec)
            assert -1.0 <= projection <= 1.0


class TestTranslationResult:
    """Tests pour TranslationResult."""

    def test_create_result(self):
        """Creer un resultat de traduction."""
        result = TranslationResult(
            text="Je suis curieux.",
            projections={'epistemic': {'curiosity': 0.72}},
            output_type="response",
            reasoning_detected=False,
            json_valid=True,
            processing_time_ms=50,
        )

        assert result.text == "Je suis curieux."
        assert result.reasoning_detected is False

    def test_to_dict(self):
        """to_dict() fonctionne."""
        result = TranslationResult(
            text="Test",
            projections={'test': {'test': 0.5}},
            output_type="response",
            reasoning_detected=True,
            json_valid=False,
            processing_time_ms=100,
        )

        d = result.to_dict()
        assert 'text' in d
        assert 'projections' in d
        assert d['reasoning_detected'] is True
        assert d['json_valid'] is False


class TestStateToLanguage:
    """Tests pour la classe StateToLanguage."""

    def test_create_translator(self):
        """Creer un traducteur."""
        translator = StateToLanguage()
        assert translator.directions == []
        assert translator._translations_count == 0

    def test_add_direction(self):
        """Ajouter des directions."""
        translator = StateToLanguage()

        direction1 = create_random_direction("curiosity", "epistemic")
        direction2 = create_random_direction("enthusiasm", "affective")

        translator.add_direction(direction1)
        translator.add_direction(direction2)

        assert len(translator.directions) == 2

    def test_project_state(self):
        """Projeter un etat sur les directions."""
        translator = StateToLanguage()

        # Ajouter des directions de categories differentes
        translator.add_direction(create_random_direction("curiosity", "epistemic"))
        translator.add_direction(create_random_direction("certainty", "epistemic"))
        translator.add_direction(create_random_direction("enthusiasm", "affective"))

        X_t = create_random_tensor()
        projections = translator.project_state(X_t)

        # Verifier structure
        assert 'epistemic' in projections
        assert 'affective' in projections
        assert 'curiosity' in projections['epistemic']
        assert 'enthusiasm' in projections['affective']

        # Verifier valeurs dans [-1, 1]
        for category, components in projections.items():
            for name, value in components.items():
                assert -1.0 <= value <= 1.0

    def test_project_state_flat(self):
        """Projection aplatie."""
        translator = StateToLanguage()
        translator.add_direction(create_random_direction("curiosity", "epistemic"))
        translator.add_direction(create_random_direction("enthusiasm", "affective"))

        X_t = create_random_tensor()
        flat = translator.project_state_flat(X_t)

        assert 'curiosity' in flat
        assert 'enthusiasm' in flat
        assert isinstance(flat['curiosity'], float)


class TestInterpretValue:
    """Tests pour interpret_value."""

    def test_very_positive(self):
        """Valeur tres positive."""
        assert StateToLanguage.interpret_value(0.8) == "tres"

    def test_moderately_positive(self):
        """Valeur moderement positive."""
        assert StateToLanguage.interpret_value(0.35) == "moderement"

    def test_neutral(self):
        """Valeur neutre."""
        assert StateToLanguage.interpret_value(0.0) == "neutre"
        assert StateToLanguage.interpret_value(-0.1) == "neutre"

    def test_moderately_negative(self):
        """Valeur moderement negative."""
        assert StateToLanguage.interpret_value(-0.35) == "peu"

    def test_very_negative(self):
        """Valeur tres negative."""
        assert StateToLanguage.interpret_value(-0.8) == "pas du tout"


class TestBuildTranslationPrompt:
    """Tests pour build_translation_prompt."""

    def test_prompt_structure(self):
        """Le prompt a la bonne structure."""
        translator = StateToLanguage()

        projections = {
            'epistemic': {'curiosity': 0.72, 'certainty': -0.18},
            'affective': {'enthusiasm': 0.45},
        }

        prompt = translator.build_translation_prompt(projections, "response")

        assert "ETAT COGNITIF" in prompt
        assert "EPISTEMIC:" in prompt
        assert "AFFECTIVE:" in prompt
        assert "curiosity" in prompt
        assert "0.72" in prompt
        assert "INSTRUCTION" in prompt
        assert "NE REFLECHIS PAS" in prompt

    def test_prompt_output_type(self):
        """Le type de sortie est inclus."""
        translator = StateToLanguage()

        prompt = translator.build_translation_prompt({}, "question")
        assert "question" in prompt


class TestZeroReasoningSystemPrompt:
    """Tests pour le system prompt zero-reasoning."""

    def test_strict_instructions(self):
        """Le prompt contient des instructions strictes."""
        translator = StateToLanguage()
        prompt = translator.build_zero_reasoning_system_prompt()

        assert "NE DOIS PAS" in prompt.upper()
        assert "RAISONNER" in prompt.upper()
        assert "CODEC" in prompt.upper()
        assert "STRICT" in prompt.upper()

    def test_no_thinking_instruction(self):
        """Instruction explicite de ne pas generer de thinking."""
        translator = StateToLanguage()
        prompt = translator.build_zero_reasoning_system_prompt()

        assert "<thinking>" in prompt.lower()


class TestJsonSystemPrompt:
    """Tests pour le system prompt JSON."""

    def test_json_schema_included(self):
        """Le schema JSON est inclus dans le prompt."""
        translator = StateToLanguage()

        schema = {
            "type": "object",
            "required": ["verbalization"],
            "properties": {"verbalization": {"type": "string"}},
        }

        prompt = translator.build_json_system_prompt(schema)

        assert "JSON" in prompt
        assert "verbalization" in prompt
        assert "UNIQUEMENT" in prompt


class TestCheckReasoningMarkers:
    """Tests pour check_reasoning_markers."""

    def test_no_markers(self):
        """Texte sans marqueurs."""
        translator = StateToLanguage()

        text = "Je suis curieux. Explorons cette idee."
        has_reasoning, markers = translator.check_reasoning_markers(text)

        assert has_reasoning is False
        assert markers == []

    def test_with_markers(self):
        """Texte avec marqueurs de raisonnement."""
        translator = StateToLanguage()

        text = "Je pense que cette approche est interessante. Apres reflexion, je suggere..."
        has_reasoning, markers = translator.check_reasoning_markers(text)

        assert has_reasoning is True
        assert "je pense que" in markers
        assert "apres reflexion" in markers

    def test_case_insensitive(self):
        """Detection insensible a la casse."""
        translator = StateToLanguage()

        text = "IL ME SEMBLE que c'est correct."
        has_reasoning, markers = translator.check_reasoning_markers(text)

        assert has_reasoning is True
        assert "il me semble" in markers


class TestTranslateSyncNoApi:
    """Tests pour translate_sync (mode test sans API)."""

    def test_translate_sync_returns_result(self):
        """translate_sync retourne un resultat."""
        translator = StateToLanguage()
        translator.add_direction(create_random_direction("curiosity", "epistemic"))

        X_t = create_random_tensor()
        result = translator.translate_sync(X_t, output_type="response")

        assert isinstance(result, TranslationResult)
        assert "[RESPONSE]" in result.text.upper()
        assert result.output_type == "response"

    def test_translate_sync_increments_count(self):
        """translate_sync incremente le compteur."""
        translator = StateToLanguage()

        initial_count = translator._translations_count

        translator.translate_sync(create_random_tensor())
        translator.translate_sync(create_random_tensor())

        assert translator._translations_count == initial_count + 2


class TestTranslateAsync:
    """Tests pour translate async avec mock."""

    def test_translate_without_client(self):
        """translate sans client retourne mock."""
        async def run_test():
            translator = StateToLanguage()
            translator.add_direction(create_random_direction("curiosity", "epistemic"))

            X_t = create_random_tensor()
            result = await translator.translate(X_t)

            assert "[MOCK TRANSLATION]" in result.text
            assert result.reasoning_detected is False

        asyncio.run(run_test())

    def test_translate_with_mock_client(self):
        """translate avec client mock."""
        async def run_test():
            # Mock du client Anthropic
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="Je suis curieux.")]
            mock_client.messages.create = AsyncMock(return_value=mock_response)

            translator = StateToLanguage(anthropic_client=mock_client)
            translator.add_direction(create_random_direction("curiosity", "epistemic"))

            X_t = create_random_tensor()
            result = await translator.translate(X_t)

            assert result.text == "Je suis curieux."
            assert mock_client.messages.create.called

            # Verifier les parametres d'appel
            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs['temperature'] == 0.0
            assert call_kwargs['max_tokens'] == 500

        asyncio.run(run_test())

    def test_translate_detects_reasoning(self):
        """translate detecte le raisonnement."""
        async def run_test():
            # Mock avec texte contenant du raisonnement
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="Je pense que c'est interessant.")]
            mock_client.messages.create = AsyncMock(return_value=mock_response)

            translator = StateToLanguage(anthropic_client=mock_client)

            X_t = create_random_tensor()
            result = await translator.translate(X_t, force_zero_reasoning=True)

            assert result.reasoning_detected is True

        asyncio.run(run_test())


class TestTranslateStructured:
    """Tests pour translate_structured (Amendment #14)."""

    def test_translate_structured_without_client(self):
        """translate_structured sans client retourne mock."""
        async def run_test():
            translator = StateToLanguage()

            X_t = create_random_tensor()
            result = await translator.translate_structured(X_t)

            assert "[MOCK JSON TRANSLATION]" in result.text

        asyncio.run(run_test())

    def test_translate_structured_valid_json(self):
        """translate_structured avec JSON valide."""
        async def run_test():
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text='{"verbalization": "Je suis curieux."}')]
            mock_client.messages.create = AsyncMock(return_value=mock_response)

            translator = StateToLanguage(anthropic_client=mock_client)

            X_t = create_random_tensor()
            result = await translator.translate_structured(X_t)

            assert result.text == "Je suis curieux."
            assert result.json_valid is True

        asyncio.run(run_test())

    def test_translate_structured_extra_fields(self):
        """translate_structured detecte les champs supplementaires."""
        async def run_test():
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(
                text='{"verbalization": "Texte", "extra": "pas autorise"}'
            )]
            mock_client.messages.create = AsyncMock(return_value=mock_response)

            translator = StateToLanguage(anthropic_client=mock_client)

            X_t = create_random_tensor()
            result = await translator.translate_structured(X_t)

            assert result.text == "Texte"
            assert result.json_valid is False

        asyncio.run(run_test())

    def test_translate_structured_invalid_json(self):
        """translate_structured gere le JSON invalide."""
        async def run_test():
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="Ceci n'est pas du JSON")]
            mock_client.messages.create = AsyncMock(return_value=mock_response)

            translator = StateToLanguage(anthropic_client=mock_client)

            X_t = create_random_tensor()
            result = await translator.translate_structured(X_t)

            assert result.json_valid is False
            assert "Ceci n'est pas du JSON" in result.text

        asyncio.run(run_test())


class TestGetStats:
    """Tests pour get_stats."""

    def test_initial_stats(self):
        """Stats initiales."""
        translator = StateToLanguage()
        stats = translator.get_stats()

        assert stats['directions_count'] == 0
        assert stats['translations_count'] == 0
        assert stats['reasoning_warnings'] == 0

    def test_stats_with_directions(self):
        """Stats avec directions."""
        translator = StateToLanguage()
        translator.add_direction(create_random_direction("curiosity", "epistemic"))
        translator.add_direction(create_random_direction("enthusiasm", "affective"))

        stats = translator.get_stats()

        assert stats['directions_count'] == 2
        assert 'epistemic' in stats['categories']
        assert 'affective' in stats['categories']


class TestCategoryToDimension:
    """Tests pour le mapping category -> dimension."""

    def test_epistemic_maps_to_firstness(self):
        """epistemic -> firstness."""
        assert CATEGORY_TO_DIMENSION['epistemic'] == 'firstness'

    def test_affective_maps_to_dispositions(self):
        """affective -> dispositions."""
        assert CATEGORY_TO_DIMENSION['affective'] == 'dispositions'

    def test_ethical_maps_to_valeurs(self):
        """ethical -> valeurs."""
        assert CATEGORY_TO_DIMENSION['ethical'] == 'valeurs'

    def test_all_categories_mapped(self):
        """Toutes les categories principales sont mappees."""
        expected_categories = [
            'epistemic', 'affective', 'cognitive', 'relational',
            'ethical', 'temporal', 'thematic', 'metacognitive',
            'vital', 'ecosystemic', 'philosophical'
        ]

        for cat in expected_categories:
            assert cat in CATEGORY_TO_DIMENSION
            assert CATEGORY_TO_DIMENSION[cat] in DIMENSION_NAMES


class TestReasoningMarkers:
    """Tests pour les marqueurs de raisonnement."""

    def test_markers_exist(self):
        """Les marqueurs existent."""
        assert len(REASONING_MARKERS) > 0

    def test_markers_are_lowercase(self):
        """Les marqueurs sont en minuscules."""
        for marker in REASONING_MARKERS:
            assert marker == marker.lower()


class TestCreateDirectionsFromConfig:
    """Tests pour create_directions_from_config."""

    def test_create_from_config(self):
        """Creer des directions depuis une config."""
        # Mock du modele d'embedding avec embeddings distincts
        np.random.seed(42)  # Pour reproductibilite
        pos_embeddings = np.random.randn(5, EMBEDDING_DIM)
        neg_embeddings = np.random.randn(5, EMBEDDING_DIM) + 1.0  # Decalage pour etre distincts

        mock_model = MagicMock()
        # Retourner des embeddings differents pour positifs et negatifs
        mock_model.encode = MagicMock(side_effect=[pos_embeddings, neg_embeddings])

        config = {
            "curiosity": {
                "category": "epistemic",
                "pole_positive": "curieux",
                "pole_negative": "desinteresse",
                "description": "Degre de curiosite",
                "positive_examples": ["a", "b", "c", "d", "e"],
                "negative_examples": ["f", "g", "h", "i", "j"],
            }
        }

        directions = create_directions_from_config(config, mock_model)

        assert len(directions) == 1
        assert directions[0].name == "curiosity"
        assert directions[0].category == "epistemic"
        assert directions[0].vector.shape == (EMBEDDING_DIM,)
        # Vecteur doit etre normalise
        assert np.isclose(np.linalg.norm(directions[0].vector), 1.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
