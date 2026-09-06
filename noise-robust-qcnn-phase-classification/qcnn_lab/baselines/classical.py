from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC


@dataclass
class ClassicalBundle:
    svm: object
    mlp: object


def make_svm(seed: int = 12345):
    return make_pipeline(
        StandardScaler(),
        SVC(C=2.0, kernel="rbf", gamma="scale", probability=True, random_state=seed),
    )


def make_mlp(seed: int = 12345):
    return make_pipeline(
        StandardScaler(),
        MLPClassifier(
            hidden_layer_sizes=(64, 32),
            max_iter=1000,
            early_stopping=True,
            random_state=seed,
        ),
    )


def fit_sklearn_baselines(X: np.ndarray, y: np.ndarray, train_idx: np.ndarray, *, seed: int = 12345) -> ClassicalBundle:
    svm = make_svm(seed)
    mlp = make_mlp(seed)
    svm.fit(X[train_idx], y[train_idx])
    mlp.fit(X[train_idx], y[train_idx])
    return ClassicalBundle(svm=svm, mlp=mlp)


def mlp_parameter_count(model) -> int:
    estimator = model.named_steps["mlpclassifier"]
    return int(sum(w.size for w in estimator.coefs_) + sum(b.size for b in estimator.intercepts_))


def svm_support_count(model) -> int:
    estimator = model.named_steps["svc"]
    return int(estimator.support_.size)


class TorchCNN1D:
    def __init__(self, in_channels: int, seed: int = 12345):
        import torch
        from torch import nn

        torch.manual_seed(seed)
        self.torch = torch
        self.model = nn.Sequential(
            nn.Conv1d(in_channels, 16, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv1d(16, 16, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
            nn.Flatten(),
            nn.Linear(16, 1),
        )

    @property
    def parameter_count(self) -> int:
        return int(sum(p.numel() for p in self.model.parameters()))

    def fit(self, X: np.ndarray, y: np.ndarray, train_idx: np.ndarray, validation_idx: np.ndarray, *, epochs: int = 250, lr: float = 0.01) -> list[dict]:
        torch = self.torch
        x = torch.tensor(X, dtype=torch.float32)
        target = torch.tensor(y, dtype=torch.float32).reshape(-1, 1)
        opt = torch.optim.Adam(self.model.parameters(), lr=lr)
        loss_fn = torch.nn.BCEWithLogitsLoss()
        history = []
        best_state = None
        best_val = float("inf")
        patience = 35
        stale = 0
        for epoch in range(epochs):
            self.model.train()
            opt.zero_grad()
            logits = self.model(x[train_idx])
            loss = loss_fn(logits, target[train_idx])
            loss.backward()
            opt.step()
            self.model.eval()
            with torch.no_grad():
                val = loss_fn(self.model(x[validation_idx]), target[validation_idx]).item()
            history.append({"epoch": epoch, "train_loss": float(loss.item()), "validation_loss": float(val)})
            if val < best_val - 1e-5:
                best_val = val
                stale = 0
                best_state = {k: v.detach().cpu().clone() for k, v in self.model.state_dict().items()}
            else:
                stale += 1
            if stale >= patience:
                break
        if best_state is not None:
            self.model.load_state_dict(best_state)
        return history

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        torch = self.torch
        self.model.eval()
        with torch.no_grad():
            logits = self.model(torch.tensor(X, dtype=torch.float32)).reshape(-1)
            return torch.sigmoid(logits).cpu().numpy()