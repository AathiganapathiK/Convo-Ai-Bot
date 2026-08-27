import React, { useState, useEffect, useCallback } from "react";
import {
  Table, Tag, Button, Space, Typography, Alert, Modal,
  Form, Input, Select, Switch, Tooltip, Badge
} from "antd";
import {
  CheckOutlined, CloseOutlined, EditOutlined, ReloadOutlined,
  ExperimentOutlined
} from "@ant-design/icons";

import { message } from "../../utils/message";
import {
  getSuggestions,
  confirmSuggestion,
  rejectSuggestion,
  getConfigOptions
} from "../../services/semanticConfigService";

import EvidencePanel from "./EvidencePanel";

const { Text, Paragraph } = Typography;
const { Option } = Select;

/**
 * Gate 2 Step 10 - the review queue for machine suggestions.
 *
 * Two rules drive the whole design:
 *
 *   1. Nothing unconfirmed may be presented as fact. Every pending row is
 *      tagged, and proposed values are rendered in a visibly provisional style
 *      that confirmed configuration never uses.
 *
 *   2. The reviewer sees a change, not a value. A suggestion for InvMonth is
 *      not "this is a month label" - it is "this is currently registered as a
 *      measure, and the proposal moves it to a dimension". The Current column
 *      beside the Proposed column is what makes that visible.
 */

const provisional = {
  fontStyle: "italic",
  color: "var(--text-secondary)"
};

const classificationColour = (c) => {
  if (c === "MEASURE") return "blue";
  if (c === "DIMENSION") return "green";
  if (c === "EXCLUDED") return "default";
  return "default";
};

export default function SuggestionsPanel({ API, token, canEdit, onConfirmed }) {
  const [loading, setLoading] = useState(false);
  const [tableSuggestions, setTableSuggestions] = useState([]);
  const [columnSuggestions, setColumnSuggestions] = useState([]);
  const [sourceStatus, setSourceStatus] = useState(null);
  const [options, setOptions] = useState({ dimension_roles: [] });

  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);

    try {
      const data = await getSuggestions(API, token);

      setTableSuggestions(data.table_suggestions || []);
      setColumnSuggestions(data.column_suggestions || []);
      setSourceStatus(data.source_status || null);
    } catch (e) {
      message.error(`Could not load suggestions: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [API, token]);

  useEffect(() => {
    load();

    getConfigOptions(API, token)
      .then(setOptions)
      .catch(() => {
        // Option lists are a convenience for the edit form. If they fail to
        // load the panel still lists and confirms suggestions, so this is not
        // worth interrupting the reviewer over.
      });
  }, [load, API, token]);

  const handleConfirm = async (record, editedProposal) => {
    setSaving(true);

    try {
      const result = await confirmSuggestion(
        API,
        token,
        record.suggestion_id,
        editedProposal
      );

      message.success(result.message || "Suggestion confirmed.");

      (result.warnings || []).forEach((w) =>
        message.warning(w, 8)
      );

      (result.notes || []).forEach((n) =>
        message.info(n, 8)
      );

      setEditing(null);
      form.resetFields();

      await load();

      if (onConfirmed) onConfirmed();
    } catch (e) {
      message.error(`Could not confirm: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleReject = (record) => {
    Modal.confirm({
      title: "Reject this suggestion?",
      content: (
        <div>
          <Paragraph style={{ marginBottom: 8 }}>
            {record.column_name
              ? `The proposal for ${record.table_name}.${record.column_name} will be removed from the queue.`
              : `The proposal for ${record.table_name} will be removed from the queue.`}
          </Paragraph>
          <Alert
            type="warning"
            showIcon
            message="This rejection is not saved"
            description={
              "Rejections are held in memory only and return when the API " +
              "restarts. Persisting them needs the suggestion evidence store " +
              "from Step 8, which is not implemented yet."
            }
          />
        </div>
      ),
      okText: "Reject anyway",
      cancelText: "Cancel",
      onOk: async () => {
        try {
          const result = await rejectSuggestion(
            API,
            token,
            record.suggestion_id,
            null
          );

          message.warning(
            result.message || "Suggestion rejected for this session."
          );

          await load();
        } catch (e) {
          message.error(`Could not reject: ${e.message}`);
        }
      }
    });
  };

  const openEditor = (record) => {
    setEditing(record);

    form.setFieldsValue({
      ...record.proposal,
      synonyms: (record.proposal?.synonyms || []).join(", ")
    });
  };

  const submitEditor = async () => {
    const values = await form.validateFields();

    const edited = { ...values };

    if (typeof edited.synonyms === "string") {
      edited.synonyms = edited.synonyms
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    }

    await handleConfirm(editing, edited);
  };

  /* ---------------------------------------------------------------- */
  /* Column suggestion table                                           */
  /* ---------------------------------------------------------------- */

  const columnColumns = [
    {
      title: "Column",
      key: "column",
      width: 220,
      render: (_, r) => (
        <div>
          <Text strong style={{ color: "var(--text-main)" }}>
            {r.column_name}
          </Text>
          <div style={{ color: "var(--text-secondary)", fontSize: 12 }}>
            {r.table_name}
          </div>
        </div>
      )
    },
    {
      title: "Currently",
      key: "current",
      width: 190,
      render: (_, r) => {
        const c = r.current || {};

        if (!c.exists) {
          return (
            <Text style={{ color: "var(--text-secondary)" }}>
              Not configured
            </Text>
          );
        }

        return (
          <Space direction="vertical" size={2}>
            <Tag color={classificationColour(c.classification)}>
              {c.classification}
            </Tag>
            <Text style={{ color: "var(--text-secondary)", fontSize: 12 }}>
              {c.business_name}
            </Text>
            {c.is_excluded && <Tag color="default">Excluded</Tag>}
          </Space>
        );
      }
    },
    {
      title: "Proposed",
      key: "proposed",
      width: 220,
      render: (_, r) => {
        const p = r.proposal || {};
        const c = r.current || {};

        const changed = c.classification !== p.classification;

        return (
          <Space direction="vertical" size={2}>
            <span>
              <Tag color={classificationColour(p.classification)}>
                {p.classification}
              </Tag>
              {changed && (
                <Tooltip title={`Changed from ${c.classification || "nothing"}`}>
                  <Tag color="purple">changed</Tag>
                </Tooltip>
              )}
            </span>
            <Text style={{ ...provisional, fontSize: 12 }}>
              {p.business_name}
            </Text>
            {p.dimension_role && (
              <Tag style={provisional}>{p.dimension_role}</Tag>
            )}
            {p.is_excluded && <Tag color="red">Exclude</Tag>}
          </Space>
        );
      }
    },
    {
      title: "Status",
      key: "status",
      width: 190,
      render: () => (
        <Tag color="orange" style={{ fontWeight: 600 }}>
          PROPOSED — NOT CONFIRMED
        </Tag>
      )
    },
    {
      title: "Action",
      key: "actions",
      width: 230,
      render: (_, r) => (
        <Space>
          <Tooltip
            title={
              canEdit
                ? "Write this proposal into the configuration"
                : "You do not have permission to modify the semantic layer"
            }
          >
            <Button
              type="primary"
              size="small"
              icon={<CheckOutlined />}
              disabled={!canEdit}
              loading={saving}
              onClick={() => handleConfirm(r, null)}
            >
              Confirm
            </Button>
          </Tooltip>

          <Button
            size="small"
            icon={<EditOutlined />}
            disabled={!canEdit}
            onClick={() => openEditor(r)}
          >
            Edit
          </Button>

          <Button
            size="small"
            danger
            icon={<CloseOutlined />}
            disabled={!canEdit}
            onClick={() => handleReject(r)}
          >
            Reject
          </Button>
        </Space>
      )
    }
  ];

  /* ---------------------------------------------------------------- */
  /* Table suggestion table                                            */
  /* ---------------------------------------------------------------- */

  const tableColumns = [
    {
      title: "Table",
      dataIndex: "table_name",
      key: "table_name",
      width: 200,
      render: (v) => (
        <Text strong style={{ color: "var(--text-main)" }}>
          {v}
        </Text>
      )
    },
    {
      title: "Proposed time behaviour",
      key: "temporal",
      render: (_, r) => {
        const p = r.proposal || {};

        return (
          <Space direction="vertical" size={2}>
            <span>
              <Tag color="blue">{p.temporal_strategy}</Tag>
              {p.domain_name && <Tag color="green">{p.domain_name}</Tag>}
            </span>
            <Text style={{ ...provisional, fontSize: 12 }}>
              Month: {p.month_column || "—"} · Sort:{" "}
              {p.month_sort_column || "—"} · Fiscal year starts month{" "}
              {p.fiscal_year_start_month}
            </Text>
            <Text style={{ ...provisional, fontSize: 12 }}>
              {(r.snapshot_mappings || []).length} period mappings proposed
            </Text>
          </Space>
        );
      }
    },
    {
      title: "Status",
      key: "status",
      width: 190,
      render: () => (
        <Tag color="orange" style={{ fontWeight: 600 }}>
          PROPOSED — NOT CONFIRMED
        </Tag>
      )
    },
    {
      title: "Action",
      key: "actions",
      width: 200,
      render: (_, r) => (
        <Space>
          <Button
            type="primary"
            size="small"
            icon={<CheckOutlined />}
            disabled={!canEdit}
            loading={saving}
            onClick={() => handleConfirm(r, null)}
          >
            Confirm
          </Button>
          <Button
            size="small"
            danger
            icon={<CloseOutlined />}
            disabled={!canEdit}
            onClick={() => handleReject(r)}
          >
            Reject
          </Button>
        </Space>
      )
    }
  ];

  const expandedTableRow = (r) => (
    <div style={{ padding: "8px 0" }}>
      <Table
        size="small"
        pagination={false}
        dataSource={(r.snapshot_mappings || []).map((m, i) => ({
          ...m,
          key: i
        }))}
        columns={[
          { title: "Offset", dataIndex: "period_offset", width: 90 },
          { title: "Kind", dataIndex: "measure_kind", width: 120 },
          {
            title: "Scope",
            dataIndex: "period_scope",
            width: 120,
            render: (v) => (
              <Tag color={v === "TO_DATE" ? "gold" : "default"}>{v}</Tag>
            )
          },
          { title: "Column", dataIndex: "column_name" }
        ]}
        style={{ marginBottom: 16, background: "var(--bg-card)" }}
        className="dark-table"
      />

      <EvidencePanel
        evidence={r.evidence}
        confidence={r.confidence}
        reasoning={r.evidence?.reasoning}
      />
    </div>
  );

  const pendingCount = tableSuggestions.length + columnSuggestions.length;

  return (
    <div>
      {sourceStatus && !sourceStatus.step_8_implemented && (
        <Alert
          type="info"
          showIcon
          icon={<ExperimentOutlined />}
          style={{ marginBottom: 16 }}
          message="Development data — the suggestion service is not built yet"
          description={
            <span>
              {sourceStatus.message} Confirming a suggestion below{" "}
              <strong>does</strong> write real configuration, so the review flow
              is genuinely testable; only the proposals themselves are stand-ins.
            </span>
          }
        />
      )}

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
          flexWrap: "wrap",
          gap: 8
        }}
      >
        <Space>
          <Badge count={pendingCount} showZero color="#d97706" />
          <Text style={{ color: "var(--text-main)", fontWeight: 600 }}>
            pending suggestions awaiting review
          </Text>
        </Space>

        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
          Refresh
        </Button>
      </div>

      {tableSuggestions.length > 0 && (
        <>
          <Text
            style={{
              color: "var(--text-secondary)",
              display: "block",
              marginBottom: 8
            }}
          >
            Table configuration
          </Text>

          <Table
            rowKey="suggestion_id"
            dataSource={tableSuggestions}
            columns={tableColumns}
            loading={loading}
            pagination={false}
            expandable={{ expandedRowRender: expandedTableRow }}
            scroll={{ x: 900 }}
            style={{ marginBottom: 24, background: "var(--bg-card)" }}
            className="dark-table"
          />
        </>
      )}

      <Text
        style={{
          color: "var(--text-secondary)",
          display: "block",
          marginBottom: 8
        }}
      >
        Column meaning — expand a row to see the evidence
      </Text>

      <Table
        rowKey="suggestion_id"
        dataSource={columnSuggestions}
        columns={columnColumns}
        loading={loading}
        pagination={{ pageSize: 10, showTotal: (t) => `Total ${t} items` }}
        expandable={{
          expandedRowRender: (r) => (
            <EvidencePanel
              evidence={r.evidence}
              confidence={r.confidence}
              reasoning={r.reasoning}
            />
          )
        }}
        scroll={{ x: 1050 }}
        style={{ background: "var(--bg-card)" }}
        className="dark-table"
        locale={{
          emptyText: (
            <div style={{ padding: 24, color: "var(--text-secondary)" }}>
              No pending suggestions.
            </div>
          )
        }}
      />

      <Modal
        title={
          <span style={{ color: "var(--text-main)" }}>
            Correct before confirming
            {editing?.column_name ? ` — ${editing.column_name}` : ""}
          </span>
        }
        open={!!editing}
        onCancel={() => {
          setEditing(null);
          form.resetFields();
        }}
        onOk={submitEditor}
        okText="Save & confirm"
        confirmLoading={saving}
        destroyOnClose
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="Your corrections are what gets saved, not the machine's proposal."
        />

        <Form form={form} layout="vertical">
          <Form.Item name="classification" label="Classification">
            <Select>
              <Option value="MEASURE">MEASURE</Option>
              <Option value="DIMENSION">DIMENSION</Option>
              <Option value="EXCLUDED">EXCLUDED</Option>
            </Select>
          </Form.Item>

          <Form.Item name="business_name" label="Business name">
            <Input />
          </Form.Item>

          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} />
          </Form.Item>

          <Form.Item
            name="synonyms"
            label="Synonyms"
            extra="Comma separated"
          >
            <Input />
          </Form.Item>

          <Form.Item name="dimension_role" label="Dimension role">
            <Select allowClear>
              {(options.dimension_roles || []).map((r) => (
                <Option key={r} value={r}>
                  {r}
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item name="aggregation_type" label="Aggregation">
            <Select allowClear>
              <Option value="SUM">SUM</Option>
              <Option value="AVG">AVG</Option>
              <Option value="COUNT">COUNT</Option>
              <Option value="MIN">MIN</Option>
              <Option value="MAX">MAX</Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="is_excluded"
            label="Exclude this column"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
