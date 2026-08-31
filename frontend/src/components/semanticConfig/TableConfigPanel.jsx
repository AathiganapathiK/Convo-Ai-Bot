import React, { useState, useEffect, useCallback } from "react";
import {
  Table, Tag, Button, Space, Typography, Modal, Form, Input,
  Select, InputNumber, Switch, Alert, Tooltip, Popconfirm
} from "antd";
import {
  EditOutlined, ReloadOutlined, PlusOutlined, DeleteOutlined,
  FieldTimeOutlined, WarningOutlined
} from "@ant-design/icons";

import { message } from "../../utils/message";
import {
  getTableConfigs,
  updateTableConfig,
  getDomains,
  getConfigOptions,
  getSnapshotMappings,
  saveSnapshotMappings
} from "../../services/semanticConfigService";

const { Text } = Typography;
const { Option } = Select;

/**
 * Gate 2 Step 10 - per-table time behaviour and period mappings.
 *
 * This is where the hardcoded year bindings go to die. The snapshot mapping
 * editor is deliberately explicit about period_scope, because FULL and TO_DATE
 * are the difference between a comparison that reports a collapse and one that
 * reports the truth. The API warns when a period has a FULL column and no
 * TO_DATE counterpart, and those warnings are surfaced here rather than
 * swallowed.
 */

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"
];

export default function TableConfigPanel({ API, token, canEdit }) {
  const [configs, setConfigs] = useState([]);
  const [domains, setDomains] = useState([]);
  const [options, setOptions] = useState({
    temporal_strategies: [],
    measure_kinds: [],
    period_scopes: []
  });

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const [editing, setEditing] = useState(null);
  const [form] = Form.useForm();
  const [strategy, setStrategy] = useState(null);

  const [mappingTable, setMappingTable] = useState(null);
  const [mappings, setMappings] = useState([]);
  const [mappingWarnings, setMappingWarnings] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);

    try {
      const [c, d] = await Promise.all([
        getTableConfigs(API, token),
        getDomains(API, token)
      ]);

      setConfigs(c);
      setDomains(d);
    } catch (e) {
      if (e.status === 400 || (e.message && e.message.includes("active database connection"))) {
        setConfigs([]);
        setDomains([]);
        message.warning("Please select an active database connection to view table configuration.");
      } else {
        message.error(`Could not load table configuration: ${e.message}`);
      }
    } finally {
      setLoading(false);
    }
  }, [API, token]);

  useEffect(() => {
    load();

    getConfigOptions(API, token)
      .then(setOptions)
      .catch(() => {});
  }, [load, API, token]);

  /* ---------------------------------------------------------------- */
  /* Table configuration                                               */
  /* ---------------------------------------------------------------- */

  const openEdit = (record) => {
    setEditing(record);
    setStrategy(record.temporal_strategy || null);

    form.setFieldsValue({
      domain_id: record.domain_id || undefined,
      temporal_strategy: record.temporal_strategy || undefined,
      date_column: record.date_column,
      month_column: record.month_column,
      month_sort_column: record.month_sort_column,
      fiscal_year_start_month: record.fiscal_year_start_month || 1,
      is_confirmed: !!record.is_confirmed
    });
  };

  const submit = async () => {
    const values = await form.validateFields();

    setSaving(true);

    try {
      await updateTableConfig(API, token, editing.table_name, values);

      message.success(`Configuration saved for ${editing.table_name}.`);

      setEditing(null);
      form.resetFields();
      await load();
    } catch (e) {
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  /* ---------------------------------------------------------------- */
  /* Snapshot mappings                                                 */
  /* ---------------------------------------------------------------- */

  const openMappings = async (record) => {
    setMappingTable(record);
    setMappingWarnings([]);

    try {
      const rows = await getSnapshotMappings(API, token, record.table_name);

      setMappings(
        rows.map((r, i) => ({ ...r, key: r.mapping_id || `row-${i}` }))
      );
    } catch (e) {
      message.error(e.message);
      setMappings([]);
    }
  };

  const addMapping = () => {
    setMappings((prev) => [
      ...prev,
      {
        key: `new-${Date.now()}`,
        period_offset: 0,
        measure_kind: "VALUE",
        period_scope: "FULL",
        column_name: "",
        is_confirmed: false
      }
    ]);
  };

  const editMapping = (key, field, value) => {
    setMappings((prev) =>
      prev.map((m) => (m.key === key ? { ...m, [field]: value } : m))
    );
  };

  const removeMapping = (key) => {
    setMappings((prev) => prev.filter((m) => m.key !== key));
  };

  const saveMappings = async () => {
    const invalid = mappings.find((m) => !m.column_name);

    if (invalid) {
      message.error("Every mapping needs a column name.");
      return;
    }

    setSaving(true);

    try {
      const result = await saveSnapshotMappings(
        API,
        token,
        mappingTable.table_name,
        mappings.map((m) => ({
          period_offset: m.period_offset,
          measure_kind: m.measure_kind,
          period_scope: m.period_scope,
          column_name: m.column_name,
          is_confirmed: !!m.is_confirmed
        }))
      );

      message.success(result.message || "Mappings saved.");

      // Warnings are shown in place rather than as a toast that vanishes: a
      // partial-period comparison is exactly the mistake this screen exists to
      // prevent, and it should stay on screen until the reviewer acts on it.
      setMappingWarnings(result.warnings || []);

      if (!(result.warnings || []).length) {
        setMappingTable(null);
      }
    } catch (e) {
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  /* ---------------------------------------------------------------- */
  /* Columns                                                           */
  /* ---------------------------------------------------------------- */

  const columns = [
    {
      title: "Table",
      key: "table_name",
      width: "25%",
      render: (_, r) => (
        <Text strong style={{ color: "var(--text-main)" }}>
          {r.table_name}
        </Text>
      )
    },
    {
      title: "Business area",
      key: "domain",
      width: "20%",
      render: (_, r) =>
        r.domain_name ? (
          <Tag color="green">{r.domain_name}</Tag>
        ) : (
          <Tooltip title="Unassigned tables are not defaulted to a domain — they fail loudly at query time.">
            <Tag color="red">Unassigned</Tag>
          </Tooltip>
        )
    },
    {
      title: "Time behaviour",
      key: "temporal",
      width: "30%",
      render: (_, r) => (
        <Space direction="vertical" size={2}>
          {r.temporal_strategy ? (
            <Tag color="blue">{r.temporal_strategy}</Tag>
          ) : (
            <Tag color="default">Not set</Tag>
          )}
          <Text style={{ color: "var(--text-secondary)", fontSize: 12 }}>
            {r.temporal_strategy === "DATE_COLUMN"
              ? `Date: ${r.date_column || "—"}`
              : `Month: ${r.month_column || "—"} · Sort: ${
                  r.month_sort_column || "—"
                }`}
          </Text>
          <Text style={{ color: "var(--text-secondary)", fontSize: 12 }}>
            Fiscal year starts:{" "}
            {MONTHS[(r.fiscal_year_start_month || 1) - 1]}
          </Text>
        </Space>
      )
    },
    {
      title: "Status",
      key: "is_confirmed",
      width: "13%",
      render: (_, r) =>
        r.is_confirmed ? (
          <Tag color="green">Confirmed</Tag>
        ) : (
          <Tag color="orange" style={{ fontWeight: 600 }}>
            UNCONFIRMED
          </Tag>
        )
    },
    {
      title: "Action",
      key: "actions",
      width: "12%",
      align: "right",
      render: (_, r) => (
        <Space>
          <Button
            size="small"
            icon={<EditOutlined />}
            disabled={!canEdit}
            onClick={() => openEdit(r)}
            aria-label={`Configure table ${r.table_name}`}
          >
            Configure
          </Button>

          <Tooltip
            title={
              r.temporal_strategy === "SNAPSHOT"
                ? "Edit the period column mappings"
                : "Mappings are only used when the strategy is SNAPSHOT"
            }
          >
            <Button
              size="small"
              icon={<FieldTimeOutlined />}
              disabled={!canEdit || r.temporal_strategy !== "SNAPSHOT"}
              onClick={() => openMappings(r)}
              aria-label={`Period mappings for ${r.table_name}`}
            >
              Mappings
            </Button>
          </Tooltip>
        </Space>
      )
    }
  ];

  /* ---------------------------------------------------------------- */
  /* Snapshot mapping columns                                          */
  /* ---------------------------------------------------------------- */

  const mappingColumns = [
    {
      title: "Offset",
      dataIndex: "period_offset",
      width: "15%",
      render: (v, r) => (
        <InputNumber
          min={0}
          value={v}
          size="small"
          disabled={!canEdit}
          onChange={(val) => editMapping(r.key, "period_offset", val ?? 0)}
          style={{ width: "100%" }}
        />
      )
    },
    {
      title: "Kind",
      dataIndex: "measure_kind",
      width: "20%",
      render: (v, r) => (
        <Select
          value={v}
          size="small"
          disabled={!canEdit}
          onChange={(val) => editMapping(r.key, "measure_kind", val)}
          style={{ width: "100%" }}
        >
          {(options.measure_kinds || ["VALUE", "QUANTITY"]).map((k) => (
            <Option key={k} value={k}>
              {k}
            </Option>
          ))}
        </Select>
      )
    },
    {
      title: "Scope",
      dataIndex: "period_scope",
      width: "22%",
      render: (v, r) => (
        <Select
          value={v}
          size="small"
          disabled={!canEdit}
          onChange={(val) => editMapping(r.key, "period_scope", val)}
          style={{ width: "100%" }}
        >
          {(options.period_scopes || ["FULL", "TO_DATE"]).map((k) => (
            <Option key={k} value={k}>
              {k}
            </Option>
          ))}
        </Select>
      )
    },
    {
      title: "Column",
      dataIndex: "column_name",
      width: "20%",
      render: (v, r) => (
        <Input
          value={v}
          size="small"
          disabled={!canEdit}
          placeholder="e.g. PYTD"
          onChange={(e) => editMapping(r.key, "column_name", e.target.value)}
        />
      )
    },
    {
      title: "",
      key: "remove",
      width: "5%",
      align: "right",
      render: (_, r) => (
        <Popconfirm
          title="Remove mapping?"
          description="Are you sure you want to remove this period mapping?"
          onConfirm={() => removeMapping(r.key)}
          okText="Remove"
          cancelText="Cancel"
          okButtonProps={{ danger: true }}
        >
          <Button
            size="small"
            danger
            type="text"
            icon={<DeleteOutlined />}
            disabled={!canEdit}
            aria-label="Remove period mapping"
          />
        </Popconfirm>
      )
    }
  ];

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          marginBottom: 16
        }}
      >
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
          Refresh
        </Button>
      </div>

      <Table
        rowKey={(r) => r.config_id || r.table_name}
        dataSource={configs}
        columns={columns}
        loading={loading}
        pagination={{ pageSize: 10, showTotal: (t) => `Total ${t} items` }}
        style={{ background: "var(--bg-card)" }}
        className="dark-table"
        locale={{
          emptyText: (
            <div style={{ padding: 24, color: "var(--text-secondary)" }}>
              No tables configured yet. Confirm a table suggestion, or configure
              one directly once discovery has run.
            </div>
          )
        }}
      />

      {/* Table configuration editor */}
      <Modal
        title={
          <span style={{ color: "var(--text-main)" }}>
            Configure {editing?.table_name}
          </span>
        }
        open={!!editing}
        onCancel={() => setEditing(null)}
        onOk={submit}
        confirmLoading={saving}
        destroyOnClose
        width={620}
        style={{ top: 30 }}
        styles={{
          body: {
            backgroundColor: "var(--bg-card)",
            maxHeight: "65vh",
            overflowY: "auto",
            padding: "16px 24px"
          }
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="domain_id" label="Business area">
            <Select allowClear placeholder="Unassigned">
              {domains.map((d) => (
                <Option key={d.domain_id} value={d.domain_id}>
                  {d.business_name}
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item
            name="temporal_strategy"
            label="How time works in this table"
            extra="SNAPSHOT — periods live in separate columns. DATE_COLUMN — filtered from a real date. NONE — no time dimension."
          >
            <Select allowClear onChange={setStrategy}>
              {(options.temporal_strategies || []).map((s) => (
                <Option key={s} value={s}>
                  {s}
                </Option>
              ))}
            </Select>
          </Form.Item>

          {strategy === "DATE_COLUMN" && (
            <Form.Item
              name="date_column"
              label="Date column"
              rules={[
                {
                  required: true,
                  message:
                    "DATE_COLUMN needs a column to filter on."
                }
              ]}
              extra="Never a load timestamp — that is when the row arrived, not when the business event happened."
            >
              <Input placeholder="e.g. InvDate" />
            </Form.Item>
          )}

          <Form.Item name="month_column" label="Month label column">
            <Input placeholder="e.g. InvMonth" />
          </Form.Item>

          <Form.Item
            name="month_sort_column"
            label="Month sort column"
            extra="Not always the same column. A label whose prefix encodes fiscal order sorts correctly as text; a calendar month number does not."
          >
            <Input placeholder="e.g. InvMonth" />
          </Form.Item>

          <Form.Item
            name="fiscal_year_start_month"
            label="Fiscal year starts in"
            extra="Never inferred from the data."
          >
            <Select>
              {MONTHS.map((m, i) => (
                <Option key={m} value={i + 1}>
                  {m}
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item
            name="is_confirmed"
            label="Mark as confirmed"
            valuePropName="checked"
            extra="Unconfirmed configuration is never treated as authoritative."
          >
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* Snapshot mapping editor */}
      <Modal
        title={
          <span style={{ color: "var(--text-main)" }}>
            Period columns — {mappingTable?.table_name}
          </span>
        }
        open={!!mappingTable}
        onCancel={() => setMappingTable(null)}
        onOk={saveMappings}
        okText="Save mappings"
        confirmLoading={saving}
        destroyOnClose
        width={780}
        style={{ top: 30 }}
        styles={{
          body: {
            backgroundColor: "var(--bg-card)",
            maxHeight: "65vh",
            overflowY: "auto",
            padding: "16px 24px"
          }
        }}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="Scope is not a detail."
          description={
            "A current period that is to-date must be compared against a " +
            "previous period that is also to-date. A full previous year and a " +
            "partial current year are two separate rows here, differing only " +
            "in scope — not a duplicate to be tidied away."
          }
        />

        {mappingWarnings.map((w, i) => (
          <Alert
            key={i}
            type="warning"
            showIcon
            icon={<WarningOutlined />}
            style={{ marginBottom: 12 }}
            message="Saved, but this comparison shape will mislead"
            description={w}
          />
        ))}

        <Table
          rowKey="key"
          dataSource={mappings}
          columns={mappingColumns}
          pagination={false}
          size="small"
          style={{ background: "var(--bg-card)", marginBottom: 12 }}
          className="dark-table"
          locale={{
            emptyText: (
              <div style={{ padding: 16, color: "var(--text-secondary)" }}>
                No period mappings yet.
              </div>
            )
          }}
        />

        <Button
          icon={<PlusOutlined />}
          onClick={addMapping}
          disabled={!canEdit}
          block
        >
          Add period mapping
        </Button>
      </Modal>
    </div>
  );
}
