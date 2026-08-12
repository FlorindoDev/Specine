from dataclasses import dataclass


ZENODO_ARCHIVE_URL = (
    "https://zenodo.org/api/records/15033911/files/Datasets.zip/content"
)
ZENODO_ARCHIVE_SIZE = 311_949_051
ZENODO_ARCHIVE_MD5 = "fbd1876b8bdad96389204a1826f17d26"


@dataclass(frozen=True)
class Benchmark:
    name: str
    display_name: str
    dataset_file: str
    dataset_family: str
    evaluation_field: str
    dataset_size: int
    dataset_crc32: int


BENCHMARKS = {
    "apps": Benchmark(
        name="apps",
        display_name="APPS",
        dataset_file="apps.jsonl",
        dataset_family="apps",
        evaluation_field="all_test_cases",
        dataset_size=684_721_893,
        dataset_crc32=2_436_324_252,
    ),
    "apps-eval": Benchmark(
        name="apps-eval",
        display_name="APPS-Eval",
        dataset_file="apps.jsonl",
        dataset_family="apps",
        evaluation_field="all_test_cases_et",
        dataset_size=684_721_893,
        dataset_crc32=2_436_324_252,
    ),
    "codecontests-raw": Benchmark(
        name="codecontests-raw",
        display_name="CodeContests-Raw",
        dataset_file="code_contests.jsonl",
        dataset_family="code_contests",
        evaluation_field="all_test_cases_raw",
        dataset_size=194_882_721,
        dataset_crc32=611_535_982,
    ),
}


def get_benchmark(name: str) -> Benchmark:
    try:
        return BENCHMARKS[name]
    except KeyError as error:
        choices = ", ".join(BENCHMARKS)
        raise ValueError(
            f"Benchmark non supportato: {name}. Valori ammessi: {choices}"
        ) from error
