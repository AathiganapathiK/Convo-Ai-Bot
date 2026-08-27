import React, { useState, useEffect, useCallback } from "react";
import {
  Table, Tag, Button, Space, Typography, Modal, Form,
  Input, Switch, Alert
} from "antd";
import { PlusOutlined, EditOutlined, ReloadOutlined } from "@ant-design/icons";

import { message } from "../../utils/message";
import {
  getDomains,
  createDomain,
  updateDomain,
  setDomainActive
} from "../../services/semanticConfigService";

const { Text } = Typography;

/**
 * Gate 2 Step 10 - business areas.
 *
 * A domain binds a business area to the tables that serve it, so a question
 * about order pendings stops resolving against the sales table, and a question
 * about products never searches geography values.
 *
 * Tables are bound to a domain from the Tables & Temporal area rather than
 * here, because the binding lives on the table's configuration row.
 */

export default function DomainsPanel({ API, token, canEdit }) {
  const [domains, setDomains] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(null);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);

    try {
      setDomains(await getDomains(API, token));
    } catch (e) {
      message.error(`Could not load domains: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [API, token]);

  useEffect(() => {
    load();
  }, [load]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ is_active: true });
    setOpen(true);
  };

  const openEdit = (record) => {
    setEditing(record);
    form.setFieldsValue(record);
    setOpen(true);
  };

  const submit = async () => {
    const values = await form.validateFields();

    setSaving(true);

    try {
      if (editing) {
        await updateDomain(API, token, editing.domain_id, values);
        message.success("Domain updated.");
      } else {
        await createDomain(API, token, values);
        message.success("Domain created.");
      }

      setOpen(false);
      form.resetFields();
      await load();
    } catch (e) {
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (record, checked) => {
    try {
      await setDomainActive(API, token, record.domain_id, checked);
      await load();
    } catch (e) {
      message.error(e.message);
    }
  };

  const columns = [
    {
      title: "Business area",
      key: "business_name",
      width: 200,
      render: (_, r) => (
        <div>
          <Text strong style={{ color: "var(--text-main)" }}>
            {r.business_name}
          </Text>
          <div style={{ color: "var(--text-secondary)", fontSize: 12 }}>
            {r.domain_name}
          </div>
        </div>
      )
    },
    {
      title: "Synonyms",
      dataIndex: "synonyms",
      key: "synonyms",
      width: 220,
      render: (v) =>
        v ? (
          <Space size={4} wrap>
            {String(v)
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean)
              .map((s) => (
                <Tag key={s}>{s}</Tag>
              ))}
          </Space>
        ) : (
          <Text style={{ color: "var(--text-secondary)" }}>—</Text>
        )
    },
    {
      title: "Description",
      dataIndex: "description",
      key: "description",
      render: (v) => (
        <Text style={{ color: "var(--text-secondary)" }}>{v || "—"}</Text>
      )
    },
    {
      title: "Active",
      key: "is_active",
      width: 110,
      render: (_, r) => (
        <Switch
          checked={!!r.is_active}
          disabled={!canEdit}
          onChange={(checked) => toggleActive(r, checked)}
          size="small"
        />
      )
    },
    {
      title: "Action",
      key: "actions",
      width: 110,
      render: (_, r) => (
        <Button
          size="small"
          icon={<EditOutlined />}
          disabled={!canEdit}
          onClick={() => openEdit(r)}
        >
          Edit
        </Button>
      )
    }
  ];

  return (
    <div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="A domain scopes a question to the right tables and values."
        description={
          "Bind tables to a domain from the Tables & Temporal area. A table " +
          "left unassigned is not treated as belonging to any domain — it " +
          "fails loudly rather than defaulting."
        }
      />

      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          gap: 8,
          marginBottom: 16
        }}
      >
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
          Refresh
        </Button>

        <Button
          type="primary"
          icon={<PlusOutlined />}
          disabled={!canEdit}
          onClick={openCreate}
        >
          New domain
        </Button>
      </div>

      <Table
        rowKey="domain_id"
        dataSource={domains}
        columns={columns}
        loading={loading}
        pagination={{ pageSize: 10, showTotal: (t) => `Total ${t} items` }}
        scroll={{ x: 850 }}
        style={{ background: "var(--bg-card)" }}
        className="dark-table"
        locale={{
          emptyText: (
            <div style={{ padding: 24, color: "var(--text-secondary)" }}>
              No business areas configured yet.
            </div>
          )
        }}
      />

      <Modal
        title={
          <span style={{ color: "var(--text-main)" }}>
            {editing ? "Edit business area" : "New business area"}
          </span>
        }
        open={open}
        onCancel={() => setOpen(false)}
        onOk={submit}
        confirmLoading={saving}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="domain_name"
            label="Domain key"
            rules={[{ required: true, message: "A domain key is required." }]}
            extra="Short internal name, e.g. Sales"
          >
            <Input />
          </Form.Item>

          <Form.Item
            name="business_name"
            label="Business name"
            rules={[{ required: true, message: "A business name is required." }]}
          >
            <Input />
          </Form.Item>

          <Form.Item
            name="synonyms"
            label="Synonyms"
            extra="Comma separated — how people actually refer to this area"
          >
            <Input />
          </Form.Item>

          <Form.Item name="description" label="Description">
            <Input.TextArea rows={3} />
          </Form.Item>

          <Form.Item name="is_active" label="Active" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
