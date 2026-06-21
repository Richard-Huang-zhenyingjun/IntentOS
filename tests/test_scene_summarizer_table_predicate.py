from src.intelligence.scene_summarizer import SceneSummarizer


def test_on_table_predicate_tolerates_small_vertical_jostle_with_table_xy():
    summarizer = SceneSummarizer(
        {
            "world": {
                "messy_table": {
                    "table_bounds_xy": [-0.35, 0.35, -0.25, 0.25],
                }
            },
            "scene_understanding": {
                "messy_detection": {
                    "z_on_table_eps": 0.04,
                    "object_height": 0.06,
                }
            },
        }
    )

    assert summarizer._is_on_table_position((0.032, 0.247, 0.703))
    assert not summarizer._is_on_table_position((0.4, 0.0, 0.75))
