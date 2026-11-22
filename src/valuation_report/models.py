"""Input schema and the math that follows from it."""

from __future__ import annotations

import statistics
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Thresholds(_Model):
    """Flag levels for comparable adjustments, in percent of sale price."""

    net_pct: float = Field(default=15.0, gt=0)
    gross_pct: float = Field(default=25.0, gt=0)


class ReportInfo(_Model):
    title: str
    report_type: Literal["evaluation", "broker_price_opinion"] = "evaluation"
    effective_date: date
    prepared_by: str
    intended_use: str
    intended_user: str
    value_premise: str = "Market value, as is, fee simple (analysis estimate)"


class Subject(_Model):
    address: str
    property_type: str
    legal_description: str = ""
    year_built: int = Field(gt=1700, lt=2200)
    gla_sqft: float = Field(gt=0)
    bedrooms: int = Field(ge=0)
    bathrooms: float = Field(ge=0)
    lot_acres: float = Field(gt=0)
    garage: str = "None"
    condition: str
    quality: str = ""
    zoning: str = ""
    occupancy: str = ""


class Site(_Model):
    size: str
    shape: str = ""
    topography: str = ""
    utilities: str = ""
    flood_zone: str = ""
    access: str = ""
    easements: str = ""


class KeyValue(_Model):
    label: str
    value: str


class Neighborhood(_Model):
    description: str
    boundaries: str = ""
    factors: list[str] = Field(default_factory=list)


class Market(_Model):
    trend: Literal["increasing", "stable", "declining"]
    summary: str
    median_days_on_market: int | None = Field(default=None, ge=0)
    months_of_supply: float | None = Field(default=None, ge=0)
    annual_price_change_pct: float | None = None


class Adjustment(_Model):
    label: str
    amount: float


class Comp(_Model):
    id: str
    address: str
    proximity: str = ""
    sale_price: float = Field(gt=0)
    sale_date: date
    data_source: str = ""
    gla_sqft: float = Field(gt=0)
    lot_acres: float = Field(gt=0)
    year_built: int = Field(gt=1700, lt=2200)
    condition: str = ""
    bedrooms: int = Field(ge=0)
    bathrooms: float = Field(ge=0)
    garage: str = "None"
    adjustments: list[Adjustment] = Field(default_factory=list)
    weight: float = Field(default=1.0, ge=0)
    stated_adjusted_price: float | None = None

    @property
    def net_adjustment(self) -> float:
        return sum(a.amount for a in self.adjustments)

    @property
    def gross_adjustment(self) -> float:
        return sum(abs(a.amount) for a in self.adjustments)

    @property
    def adjusted_price(self) -> float:
        return self.sale_price + self.net_adjustment

    @property
    def net_pct(self) -> float:
        return self.net_adjustment / self.sale_price * 100

    @property
    def gross_pct(self) -> float:
        return self.gross_adjustment / self.sale_price * 100

    @property
    def price_per_sqft(self) -> float:
        return self.sale_price / self.gla_sqft

    @property
    def adjusted_per_sqft(self) -> float:
        return self.adjusted_price / self.gla_sqft


class CostItem(_Model):
    label: str
    quantity: float = Field(gt=0)
    unit: str = "sq ft"
    unit_cost: float = Field(ge=0)

    @property
    def total(self) -> float:
        return self.quantity * self.unit_cost


class Depreciation(_Model):
    physical_pct: float = Field(default=0, ge=0, le=100)
    functional: float = Field(default=0, ge=0)
    external: float = Field(default=0, ge=0)


class CostApproach(_Model):
    land_value: float = Field(ge=0)
    land_value_source: str = ""
    items: list[CostItem]
    depreciation: Depreciation = Field(default_factory=Depreciation)
    stated_indicated_value: float | None = None

    @property
    def replacement_cost_new(self) -> float:
        return sum(i.total for i in self.items)

    @property
    def physical_depreciation(self) -> float:
        return self.replacement_cost_new * self.depreciation.physical_pct / 100

    @property
    def total_depreciation(self) -> float:
        d = self.depreciation
        return self.physical_depreciation + d.functional + d.external

    @property
    def depreciated_improvements(self) -> float:
        return self.replacement_cost_new - self.total_depreciation

    @property
    def indicated_value(self) -> float:
        return self.land_value + self.depreciated_improvements


class RentalComp(_Model):
    id: str
    address: str
    sale_price: float = Field(gt=0)
    monthly_rent: float = Field(gt=0)

    @property
    def grm(self) -> float:
        return self.sale_price / self.monthly_rent


class IncomeApproach(_Model):
    monthly_market_rent: float = Field(gt=0)
    rent_comps: list[RentalComp]
    selected_grm: float = Field(gt=0)
    stated_indicated_value: float | None = None

    @property
    def grm_low(self) -> float:
        return min(c.grm for c in self.rent_comps)

    @property
    def grm_high(self) -> float:
        return max(c.grm for c in self.rent_comps)

    @property
    def grm_median(self) -> float:
        return statistics.median(c.grm for c in self.rent_comps)

    @property
    def indicated_value(self) -> float:
        return self.monthly_market_rent * self.selected_grm


class Reconciliation(_Model):
    weights: dict[Literal["sales_comparison", "cost", "income"], float]
    opinion_of_value: float = Field(gt=0)
    narrative: str
    range_low: float | None = Field(default=None, gt=0)
    range_high: float | None = Field(default=None, gt=0)


class Photo(_Model):
    path: str
    caption: str


class Report(_Model):
    report: ReportInfo
    subject: Subject
    site: Site
    improvements: list[KeyValue] = Field(default_factory=list)
    neighborhood: Neighborhood
    market: Market
    scope_of_work: str
    comparable_sales: list[Comp]
    thresholds: Thresholds = Field(default_factory=Thresholds)
    cost_approach: CostApproach | None = None
    income_approach: IncomeApproach | None = None
    reconciliation: Reconciliation
    photos: list[Photo] = Field(default_factory=list)
    map_image: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    limiting_conditions: list[str] = Field(default_factory=list)

    @property
    def sales_indication(self) -> float:
        total_w = sum(c.weight for c in self.comparable_sales)
        if total_w == 0:
            return 0.0
        return sum(c.adjusted_price * c.weight for c in self.comparable_sales) / total_w

    def indications(self) -> dict[str, float]:
        out: dict[str, float] = {"sales_comparison": self.sales_indication}
        if self.cost_approach:
            out["cost"] = self.cost_approach.indicated_value
        if self.income_approach:
            out["income"] = self.income_approach.indicated_value
        return out

    @property
    def weighted_value(self) -> float:
        ind = self.indications()
        w = self.reconciliation.weights
        return sum(ind[k] * w[k] for k in w if k in ind)
