import torch
import torch.nn as nn

class Autoencoder(nn.Module):
    """Squeezes 5 numbers down to 3, then rebuilds them.
    Trained only on normal data, so it rebuilds normal rows well
    and unusual rows badly."""
    def __init__(self, n_features: int = 5):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(n_features, 12), nn.ReLU(), nn.Linear(12, 3))
        self.decoder = nn.Sequential(
            nn.Linear(3, 12), nn.ReLU(), nn.Linear(12, n_features))

    def forward(self, x):
        return self.decoder(self.encoder(x))

def reconstruction_error(model: nn.Module, x: torch.Tensor):
    """Returns (score per row, error per feature per row)."""
    model.eval()
    with torch.no_grad():
        per_feature = (model(x) - x) ** 2
    return per_feature.mean(dim=1), per_feature

if __name__ == "__main__":
    m = Autoencoder()
    print("parameters:", sum(p.numel() for p in m.parameters()))
    score, per_feature = reconstruction_error(m, torch.randn(4, 5))
    print("score shape:", tuple(score.shape), "| per-feature shape:", tuple(per_feature.shape))