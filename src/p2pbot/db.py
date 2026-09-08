from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Float, Integer, Numeric, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .domain import Ad, Opportunity


class Base(DeclarativeBase):
    pass


class MerchantRow(Base):
    __tablename__ = "merchants"
    merchant_no: Mapped[str] = mapped_column(String(128), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(255))
    completion_rate_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    order_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_release_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    merchant_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AdSnapshotRow(Base):
    __tablename__ = "ad_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ad_no: Mapped[str] = mapped_column(String(128), index=True)
    merchant_no: Mapped[str] = mapped_column(String(128), index=True)
    trade_type: Mapped[str] = mapped_column(String(8), index=True)
    asset: Mapped[str] = mapped_column(String(20), index=True)
    fiat: Mapped[str] = mapped_column(String(20), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    available_asset: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    min_fiat: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    max_fiat: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    payment_methods_json: Mapped[str] = mapped_column(Text, default="[]")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    raw_json: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("ad_no", "trade_type", "observed_at", name="uq_ad_observation"),)


class OpportunityRow(Base):
    __tablename__ = "opportunities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    buy_ad_no: Mapped[str] = mapped_column(String(128), index=True)
    sell_ad_no: Mapped[str] = mapped_column(String(128), index=True)
    buy_merchant_no: Mapped[str] = mapped_column(String(128))
    sell_merchant_no: Mapped[str] = mapped_column(String(128))
    asset: Mapped[str] = mapped_column(String(20))
    fiat: Mapped[str] = mapped_column(String(20))
    asset_amount: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    buy_price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    sell_price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    gross_profit_fiat: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    net_profit_fiat: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    net_roi_pct: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    buy_merchant_score: Mapped[float] = mapped_column(Float)
    sell_merchant_score: Mapped[float] = mapped_column(Float)
    common_payment_methods_json: Mapped[str] = mapped_column(Text, default="[]")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Repository:
    def __init__(self, database_url: str):
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, future=True, pool_pre_ping=True, connect_args=connect_args)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def save_ads(self, ads: list[Ad]) -> None:
        with Session(self.engine) as session:
            for ad in ads:
                merchant = session.get(MerchantRow, ad.merchant.merchant_no)
                if merchant is None:
                    merchant = MerchantRow(
                        merchant_no=ad.merchant.merchant_no,
                        nickname=ad.merchant.nickname,
                        updated_at=ad.observed_at,
                    )
                    session.add(merchant)
                merchant.nickname = ad.merchant.nickname
                merchant.completion_rate_pct = ad.merchant.completion_rate_pct
                merchant.order_count = ad.merchant.order_count
                merchant.avg_release_seconds = ad.merchant.avg_release_seconds
                merchant.merchant_type = ad.merchant.merchant_type
                merchant.updated_at = ad.observed_at

                session.add(
                    AdSnapshotRow(
                        ad_no=ad.ad_no,
                        merchant_no=ad.merchant.merchant_no,
                        trade_type=ad.trade_type,
                        asset=ad.asset,
                        fiat=ad.fiat,
                        price=ad.price,
                        available_asset=ad.available_asset,
                        min_fiat=ad.min_fiat,
                        max_fiat=ad.max_fiat,
                        payment_methods_json=json.dumps(ad.payment_methods),
                        observed_at=ad.observed_at,
                        raw_json=json.dumps(ad.raw, ensure_ascii=False, default=str),
                    )
                )
            session.commit()

    def save_opportunities(self, opportunities: list[Opportunity]) -> None:
        with Session(self.engine) as session:
            for op in opportunities:
                session.add(
                    OpportunityRow(
                        buy_ad_no=op.buy_ad_no,
                        sell_ad_no=op.sell_ad_no,
                        buy_merchant_no=op.buy_merchant_no,
                        sell_merchant_no=op.sell_merchant_no,
                        asset=op.asset,
                        fiat=op.fiat,
                        asset_amount=op.asset_amount,
                        buy_price=op.buy_price,
                        sell_price=op.sell_price,
                        gross_profit_fiat=op.gross_profit_fiat,
                        net_profit_fiat=op.net_profit_fiat,
                        net_roi_pct=op.net_roi_pct,
                        buy_merchant_score=op.buy_merchant_score,
                        sell_merchant_score=op.sell_merchant_score,
                        common_payment_methods_json=json.dumps(op.common_payment_methods),
                        observed_at=op.observed_at,
                    )
                )
            session.commit()

    def recent_opportunities(self, limit: int = 50) -> list[dict]:
        with Session(self.engine) as session:
            rows = session.scalars(select(OpportunityRow).order_by(OpportunityRow.id.desc()).limit(limit)).all()
            return [
                {
                    "buy_ad_no": r.buy_ad_no,
                    "sell_ad_no": r.sell_ad_no,
                    "asset": r.asset,
                    "fiat": r.fiat,
                    "asset_amount": str(r.asset_amount),
                    "buy_price": str(r.buy_price),
                    "sell_price": str(r.sell_price),
                    "net_profit_fiat": str(r.net_profit_fiat),
                    "net_roi_pct": str(r.net_roi_pct),
                    "buy_merchant_score": r.buy_merchant_score,
                    "sell_merchant_score": r.sell_merchant_score,
                    "common_payment_methods": json.loads(r.common_payment_methods_json),
                    "observed_at": r.observed_at.isoformat(),
                }
                for r in rows
            ]
