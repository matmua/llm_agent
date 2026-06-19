"""WebShop environment adapters.

The official adapter is used when the original WebShop package and data are
installed. The mock adapter implements the same minimal interface so the shadow
pipeline can be tested without external data or API keys.
"""

from __future__ import annotations

import copy
import os
import random
import sys
from dataclasses import dataclass
from typing import Any


class WebShopEnvProtocol:
    def reset(self, task_index: int) -> str:
        raise NotImplementedError

    def step(self, action: str) -> tuple[str, float, bool, Any]:
        raise NotImplementedError

    def get_available_actions(self) -> dict[str, Any]:
        raise NotImplementedError

    def get_instruction_text(self) -> str:
        raise NotImplementedError

    @property
    def env_name(self) -> str:
        return self.__class__.__name__


class OfficialWebShopEnv(WebShopEnvProtocol):
    def __init__(self, repo_path: str = "external/webshop", num_products: int = 1000):
        repo_abs = os.path.abspath(repo_path)
        if repo_abs not in sys.path:
            sys.path.insert(0, repo_abs)
        _configure_conda_java()
        try:
            import gym  # type: ignore
            import numpy as np  # type: ignore
            import web_agent_site.envs  # noqa: F401
        except Exception as exc:  # pragma: no cover - depends on optional deps
            raise RuntimeError(
                "Official WebShop dependencies are not installed. "
                "Run external/webshop/setup.sh in a compatible Python 3.8 env."
            ) from exc
        random.seed(233)
        np.random.seed(233)
        self._env = gym.make(
            "WebAgentTextEnv-v0",
            observation_mode="text",
            num_products=num_products,
        )

    def reset(self, task_index: int) -> str:
        observation, _ = self._env.reset(session=task_index)
        return observation

    def step(self, action: str) -> tuple[str, float, bool, Any]:
        observation, reward, done, info = self._env.step(action)
        return observation, float(reward), bool(done), info

    def get_available_actions(self) -> dict[str, Any]:
        return self._env.get_available_actions()

    def get_instruction_text(self) -> str:
        return self._env.get_instruction_text()


@dataclass
class MockProduct:
    name: str
    product_type: str
    price: float
    brand: str
    color: str
    size: str
    description: str
    rating: float


@dataclass
class MockTask:
    instruction: str
    product_type: str
    constraints: dict[str, Any]


class MockWebShopEnv(WebShopEnvProtocol):
    def __init__(self) -> None:
        self.products = _mock_products()
        self.tasks = _mock_tasks()
        self.task: MockTask = self.tasks[0]
        self.page = "search"
        self.query = ""
        self.results: list[MockProduct] = []
        self.current: MockProduct | None = None
        self.done = False
        self.last_observation = ""

    @property
    def env_name(self) -> str:
        return "mock_webshop"

    def reset(self, task_index: int) -> str:
        self.task = copy.deepcopy(self.tasks[task_index % len(self.tasks)])
        self.page = "search"
        self.query = ""
        self.results = []
        self.current = None
        self.done = False
        self.last_observation = self._render()
        return self.last_observation

    def step(self, action: str) -> tuple[str, float, bool, Any]:
        if self.done:
            return self.last_observation, 0.0, True, {"message": "episode already done"}
        normalized = action.strip().lower()
        reward = 0.0
        info: dict[str, Any] = {}
        if normalized.startswith("search[") and normalized.endswith("]"):
            self.query = action[action.find("[") + 1 : -1].strip().lower()
            self.results = self._search(self.query)
            self.page = "results"
            self.current = None
        elif normalized.startswith("click[") and normalized.endswith("]"):
            target = action[action.find("[") + 1 : -1].strip().lower()
            clickables = {item.lower(): item for item in self.get_available_actions().get("clickables", [])}
            if target not in clickables:
                info["invalid_action"] = True
            elif target in {"description", "features", "reviews"} and self.current:
                self.page = target
            elif target == "back to search":
                self.page = "search"
                self.current = None
            elif target == "buy now" and self.current:
                reward = 1.0 if self._matches_task(self.current) else 0.0
                self.done = True
                self.page = "done"
                info["purchased"] = self.current.name
                info["matched_constraints"] = reward > 0
            else:
                selected = self._product_by_name(target)
                if selected:
                    self.current = selected
                    self.page = "product"
        else:
            info["invalid_action"] = True
        self.last_observation = self._render(reward=reward)
        return self.last_observation, reward, self.done, info

    def get_available_actions(self) -> dict[str, Any]:
        if self.page == "search":
            return {"has_search_bar": True, "clickables": []}
        if self.page == "results":
            return {
                "has_search_bar": True,
                "clickables": [product.name for product in self.results] + ["back to search"],
            }
        if self.page in {"product", "description", "features", "reviews"}:
            return {
                "has_search_bar": False,
                "clickables": ["description", "features", "reviews", "buy now", "back to search"],
            }
        return {"has_search_bar": False, "clickables": []}

    def get_instruction_text(self) -> str:
        return self.task.instruction

    def _search(self, query: str) -> list[MockProduct]:
        tokens = set(query.split())
        scored = []
        for product in self.products:
            haystack = " ".join(
                [
                    product.name,
                    product.product_type,
                    product.brand,
                    product.color,
                    product.size,
                    product.description,
                ]
            ).lower()
            score = sum(1 for token in tokens if token in haystack)
            if self.task.product_type in haystack:
                score += 1
            if score:
                scored.append((score, product))
        scored.sort(key=lambda item: (-item[0], item[1].price))
        return [product for _, product in scored[:4]] or self.products[:4]

    def _product_by_name(self, target: str) -> MockProduct | None:
        for product in self.products:
            if product.name.lower() == target:
                return product
        return None

    def _matches_task(self, product: MockProduct) -> bool:
        constraints = self.task.constraints
        if product.product_type != self.task.product_type:
            return False
        if "price_max" in constraints and product.price > float(constraints["price_max"]):
            return False
        for attr in ("brand", "color", "size"):
            if attr in constraints and getattr(product, attr) != constraints[attr]:
                return False
        for token in constraints.get("description_contains", []):
            if token not in product.description.lower():
                return False
        return True

    def _render(self, reward: float = 0.0) -> str:
        instruction = f"Instruction: {self.task.instruction}"
        if self.page == "search":
            return f"{instruction} [SEP] Search page [SEP] Search"
        if self.page == "results":
            lines = [instruction, f"Search results for: {self.query}"]
            for product in self.results:
                lines.append(f"{product.name} - ${product.price:.2f} - {product.brand}")
            return " [SEP] ".join(lines)
        if self.page == "product" and self.current:
            product = self.current
            return (
                f"{instruction} [SEP] {product.name} [SEP] Price: ${product.price:.2f} "
                f"[SEP] Brand: {product.brand} [SEP] Rating: {product.rating:.1f} "
                "[SEP] description [SEP] features [SEP] reviews [SEP] buy now"
            )
        if self.page in {"description", "features", "reviews"} and self.current:
            product = self.current
            return (
                f"{instruction} [SEP] {product.name} [SEP] Price: ${product.price:.2f} "
                f"[SEP] Brand: {product.brand} [SEP] Color: {product.color} "
                f"[SEP] Size: {product.size} [SEP] Details: {product.description} "
                "[SEP] buy now"
            )
        if self.page == "done":
            purchased = self.current.name if self.current else "none"
            return f"{instruction} [SEP] Done [SEP] Purchased: {purchased} [SEP] Score: {reward:.1f}"
        return instruction


def make_webshop_env(kind: str, repo_path: str = "external/webshop", num_products: int = 1000) -> WebShopEnvProtocol:
    if kind == "mock":
        return MockWebShopEnv()
    if kind == "official":
        return OfficialWebShopEnv(repo_path=repo_path, num_products=num_products)
    if kind == "auto":
        try:
            return OfficialWebShopEnv(repo_path=repo_path, num_products=num_products)
        except RuntimeError:
            return MockWebShopEnv()
    raise ValueError(f"Unknown env kind: {kind}")


def _configure_conda_java() -> None:
    env_prefix = sys.prefix
    env_bin = os.path.join(env_prefix, "bin")
    if os.path.isdir(env_bin):
        os.environ["PATH"] = env_bin + os.pathsep + os.environ.get("PATH", "")
    libjvm = os.path.join(env_prefix, "lib", "jvm", "lib", "server", "libjvm.so")
    if os.path.exists(libjvm):
        os.environ.setdefault("JAVA_HOME", env_prefix)
        os.environ.setdefault("JVM_PATH", libjvm)


def _mock_products() -> list[MockProduct]:
    return [
        MockProduct("Red Ceramic Mug", "mug", 14.99, "homecraft", "red", "medium", "dishwasher safe ceramic mug", 4.6),
        MockProduct("Blue Travel Mug", "mug", 18.50, "roadmate", "blue", "large", "insulated stainless travel mug", 4.4),
        MockProduct("Cotton Yoga Shirt", "shirt", 22.00, "softline", "white", "medium", "organic cotton breathable shirt", 4.5),
        MockProduct("Black Running Shoes", "shoes", 64.99, "swiftstep", "black", "large", "lightweight running shoes", 4.3),
        MockProduct("Wireless Mouse Pro", "mouse", 29.99, "clicklab", "black", "small", "wireless rechargeable mouse", 4.7),
        MockProduct("Silver Water Bottle", "bottle", 16.25, "pureflow", "silver", "large", "stainless waterproof bottle", 4.8),
        MockProduct("Green Garden Gloves", "gloves", 12.50, "groweasy", "green", "medium", "cotton garden gloves", 4.2),
        MockProduct("Budget Blue Shirt", "shirt", 12.99, "basicwear", "blue", "large", "polyester casual shirt", 4.0),
    ]


def _mock_tasks() -> list[MockTask]:
    return [
        MockTask("Find a red mug under $20.", "mug", {"color": "red", "price_max": 20}),
        MockTask("Buy a wireless rechargeable mouse under $35.", "mouse", {"price_max": 35, "description_contains": ["wireless", "rechargeable"]}),
        MockTask("Find an organic cotton shirt in medium size.", "shirt", {"size": "medium", "description_contains": ["organic", "cotton"]}),
        MockTask("Purchase a silver stainless water bottle below $25.", "bottle", {"color": "silver", "price_max": 25, "description_contains": ["stainless"]}),
        MockTask("Find black running shoes under $70.", "shoes", {"color": "black", "price_max": 70}),
        MockTask("Buy green medium garden gloves.", "gloves", {"color": "green", "size": "medium"}),
        MockTask("Find a blue shirt under $15.", "shirt", {"color": "blue", "price_max": 15}),
        MockTask("Purchase a large blue mug under $20.", "mug", {"color": "blue", "size": "large", "price_max": 20}),
        MockTask("Buy a black wireless mouse.", "mouse", {"color": "black", "description_contains": ["wireless"]}),
        MockTask("Find a dishwasher safe red ceramic mug.", "mug", {"color": "red", "description_contains": ["dishwasher", "ceramic"]}),
    ]
