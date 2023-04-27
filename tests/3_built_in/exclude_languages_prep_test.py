#!/usr/bin/env python
import pytest

import colrev.ops.built_in.prep.exclude_languages
import colrev.ops.prep


@pytest.fixture(scope="package")
def prep_operation(
    base_repo_review_manager: colrev.review_manager.ReviewManager,
) -> colrev.ops.prep.Prep:
    return base_repo_review_manager.get_prep_operation()


@pytest.fixture(scope="package")
def elp(
    prep_operation: colrev.ops.prep.Prep,
) -> colrev.ops.built_in.prep.exclude_languages.ExcludeLanguagesPrep:
    settings = {"endpoint": "colrev.exclude_languages"}
    elp_instance = colrev.ops.built_in.prep.exclude_languages.ExcludeLanguagesPrep(
        prep_operation=prep_operation, settings=settings
    )
    return elp_instance


@pytest.mark.parametrize(
    "input_value, expected",
    [
        (
            {
                "title": "An Integrated Framework for Understanding Digital Work in Organizations",
            },
            {
                "title": "An Integrated Framework for Understanding Digital Work in Organizations",
                "language": "eng",
                "colrev_data_provenance": {
                    "language": {"note": "", "source": "LanguageDetector"}
                },
            },
        ),
        (
            {
                "title": 'Corrigendum to "Joint collaborative planning as a governance mechanism to strengthen the chain of IT value co-creation" [J. Strategic Inf. Syst. 21(3) (2012) 182-200]',
            },
            {
                "title": 'Corrigendum to "Joint collaborative planning as a governance mechanism to strengthen the chain of IT value co-creation" [J. Strategic Inf. Syst. 21(3) (2012) 182-200]',
                "language": "eng",
                "colrev_data_provenance": {
                    "language": {"note": "", "source": "LanguageDetector"}
                },
            },
        ),
        (
            {
                "title": "A discussion about Action Research studies and their variations in Smart Cities and the challenges in Latin America [Uma discussão sobre o uso da Pesquisa-Ação e suas variações em estudos sobre Cidades Inteligentes e os desafios na América Latina]"
            },
            {
                "title": "A discussion about Action Research studies and their variations in Smart Cities and the challenges in Latin America",
                "title_por": "Uma discussão sobre o uso da Pesquisa-Ação e suas variações em estudos sobre Cidades Inteligentes e os desafios na América Latina",
                "colrev_data_provenance": {
                    "language": {"note": "", "source": "LanguageDetector_split"},
                    "title_por": {"note": "", "source": "LanguageDetector_split"},
                },
                "colrev_masterdata_provenance": {
                    "title": {"note": "", "source": "original|LanguageDetector_split"}
                },
                "language": "eng",
            },
        ),
        (
            {
                "title": "Coliving housing: home cultures of precarity for the new creative class [Alojamiento en convivencia: culturas domésticas de la precariedad para la nueva clase creativa] [La vie en colocation : les cultures du domicile issues de la précarité et la nouvelle classe créative]"
            },
            {
                "title": "Coliving housing: home cultures of precarity for the new creative class",
                "title_spa": "Alojamiento en convivencia: culturas domésticas de la precariedad para la nueva clase creativa",
                "title_fra": "La vie en colocation : les cultures du domicile issues de la précarité et la nouvelle classe créative",
                "colrev_data_provenance": {
                    "language": {"note": "", "source": "LanguageDetector_split"},
                    "title_fra": {"note": "", "source": "LanguageDetector_split"},
                    "title_spa": {"note": "", "source": "LanguageDetector_split"},
                },
                "colrev_masterdata_provenance": {
                    "title": {"note": "", "source": "original|LanguageDetector_split"}
                },
                "language": "eng",
            },
        ),
    ],
)
def test_prep_exclude_languages(
    elp: colrev.ops.built_in.prep.exclude_languages.ExcludeLanguagesPrep,
    input_value: dict,
    expected: dict,
) -> None:
    record = colrev.record.PrepRecord(data=input_value)
    returned_record = elp.prepare(prep_operation=elp, record=record)
    actual = returned_record.data
    assert expected == actual
