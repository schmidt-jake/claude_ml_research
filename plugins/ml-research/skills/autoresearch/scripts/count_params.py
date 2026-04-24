import json
from pathlib import Path

import torch
import yaml
from jsonargparse import ArgumentParser, Namespace
from metabolo_genes.models.single_cell import SingleCellModel


def main(config_path: Path = Path("config", "conf.yaml")) -> None:
    parser = ArgumentParser()
    parser.add_class_arguments(SingleCellModel, "model")

    with config_path.open() as f:
        raw = yaml.safe_load(f)

    cfg = parser.parse_object(Namespace(model=raw["model"]))

    with torch.device("meta"):
        model = parser.instantiate_classes(cfg).model
        model.build_model()

    num_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    num_total = sum(p.numel() for p in model.parameters())

    print(
        json.dumps(
            {
                "trainable_params": num_trainable,
                "total_params": num_total,
                "frozen_params": num_total - num_trainable,
            }
        )
    )


if __name__ == "__main__":
    main()
