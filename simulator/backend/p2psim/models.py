from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SimulationRow(Base):
    __tablename__ = "simulations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    seed: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    config_json: Mapped[str] = mapped_column(Text)
    config_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    base_simulated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    base_real_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    speed: Mapped[float] = mapped_column(Float, default=1.0)
    market_tick_index: Mapped[int] = mapped_column(Integer, default=0)
    market_frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    regime: Mapped[str] = mapped_column(String(32), default="NORMAL")


class MerchantProfileRow(Base):
    __tablename__ = "merchant_profiles"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    config_json: Mapped[str] = mapped_column(Text)


class MerchantRow(Base):
    __tablename__ = "sim_merchants"
    merchant_no: Mapped[str] = mapped_column(String(64), primary_key=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id"), index=True)
    nickname: Mapped[str] = mapped_column(String(128))
    merchant_type: Mapped[str] = mapped_column(String(32), default="MERCHANT")
    verified: Mapped[bool] = mapped_column(Boolean, default=True)
    completion_rate_pct: Mapped[float] = mapped_column(Float)
    order_count: Mapped[int] = mapped_column(Integer)
    avg_release_seconds: Mapped[float] = mapped_column(Float)
    profile_name: Mapped[str] = mapped_column(String(64))
    profile_version: Mapped[int] = mapped_column(Integer, default=1)
    online: Mapped[bool] = mapped_column(Boolean, default=True)
    buy_offset_bps: Mapped[float] = mapped_column(Float, default=0.0)
    sell_offset_bps: Mapped[float] = mapped_column(Float, default=0.0)
    payment_methods_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PaymentMethodRow(Base):
    __tablename__ = "payment_methods"
    identifier: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128))
    fiat: Mapped[str] = mapped_column(String(16), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class PriceTickRow(Base):
    __tablename__ = "price_ticks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id"), index=True)
    asset: Mapped[str] = mapped_column(String(16))
    fiat: Mapped[str] = mapped_column(String(16))
    price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    regime: Mapped[str] = mapped_column(String(32))
    tick_index: Mapped[int] = mapped_column(Integer)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    __table_args__ = (UniqueConstraint("simulation_id", "tick_index", name="uq_sim_tick"),)


class AdRow(Base):
    __tablename__ = "sim_ads"
    ad_no: Mapped[str] = mapped_column(String(64), primary_key=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id"), index=True)
    merchant_no: Mapped[str] = mapped_column(ForeignKey("sim_merchants.merchant_no"), index=True)
    trade_type: Mapped[str] = mapped_column(String(8), index=True)
    asset: Mapped[str] = mapped_column(String(16), index=True)
    fiat: Mapped[str] = mapped_column(String(16), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    total_asset: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    min_fiat: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    max_fiat: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    payment_methods_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BalanceRow(Base):
    __tablename__ = "sim_balances"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id"), index=True)
    account_id: Mapped[str] = mapped_column(String(128), index=True)
    currency: Mapped[str] = mapped_column(String(16), index=True)
    owned: Mapped[Decimal] = mapped_column(Numeric(30, 10), default=0)
    reserved: Mapped[Decimal] = mapped_column(Numeric(30, 10), default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("simulation_id", "account_id", "currency", name="uq_balance"),)


class ReservationRow(Base):
    __tablename__ = "sim_reservations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id"), index=True)
    order_no: Mapped[str] = mapped_column(String(64), index=True)
    account_id: Mapped[str] = mapped_column(String(128))
    currency: Mapped[str] = mapped_column(String(16))
    amount: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("order_no", "kind", name="uq_order_reservation_kind"),)


class LedgerEntryRow(Base):
    __tablename__ = "sim_ledger"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    order_no: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(16))
    amount: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    from_account: Mapped[str] = mapped_column(String(128))
    to_account: Mapped[str] = mapped_column(String(128))
    entry_type: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class OrderRow(Base):
    __tablename__ = "sim_orders"
    order_no: Mapped[str] = mapped_column(String(64), primary_key=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id"), index=True)
    ad_no: Mapped[str] = mapped_column(String(64), index=True)
    bot_trade_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    side: Mapped[str] = mapped_column(String(8), index=True)
    buyer_account: Mapped[str] = mapped_column(String(128))
    seller_account: Mapped[str] = mapped_column(String(128))
    merchant_no: Mapped[str] = mapped_column(String(64), index=True)
    merchant_profile: Mapped[str] = mapped_column(String(64))
    asset: Mapped[str] = mapped_column(String(16))
    fiat: Mapped[str] = mapped_column(String(16))
    asset_amount: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    fiat_amount: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    payment_method: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40), index=True)
    outgoing_payment_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    incoming_verification_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payment_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrderEventRow(Base):
    __tablename__ = "sim_order_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id"), index=True)
    order_no: Mapped[str] = mapped_column(String(64), index=True)
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class DomainEventRow(Base):
    __tablename__ = "sim_domain_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ScheduledEventRow(Base):
    __tablename__ = "scheduled_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class PaymentEvidenceRow(Base):
    __tablename__ = "payment_evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id"), index=True)
    order_no: Mapped[str] = mapped_column(String(64), index=True)
    evidence_id: Mapped[str] = mapped_column(String(128), unique=True)
    direction: Mapped[str] = mapped_column(String(8))
    amount: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    currency: Mapped[str] = mapped_column(String(16))
    counterparty: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    scenario: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ChatMessageRow(Base):
    __tablename__ = "sim_chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id"), index=True)
    order_no: Mapped[str] = mapped_column(String(64), index=True)
    sender: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text)
    client_idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DisputeRow(Base):
    __tablename__ = "sim_disputes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id"), index=True)
    order_no: Mapped[str] = mapped_column(String(64), unique=True)
    reason: Mapped[str] = mapped_column(String(128))
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="OPEN")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(32), nullable=True)


class FaultRow(Base):
    __tablename__ = "sim_faults"
    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    remaining: Mapped[int] = mapped_column(Integer, default=1)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IdempotencyRow(Base):
    __tablename__ = "sim_idempotency"
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id"), index=True)
    operation: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AdminActionRow(Base):
    __tablename__ = "sim_admin_actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id"), index=True)
    action: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
