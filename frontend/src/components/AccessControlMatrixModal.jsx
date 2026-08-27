import React, { useState, useEffect } from "react";
import {
  Modal, Tabs, Select, Table, Checkbox, Switch, Button, Tag, Space,
  Typography, Card, Divider, Spin, Tooltip
} from "antd";
import {
  Shield, Users, Lock, CheckCircle, Eye, Edit3, MessageSquare, Database,
  Globe, Package, ShoppingBag, Layers
} from "lucide-react";
import { message } from "../utils/message";

const { Text, Title } = Typography;
const { Option } = Select;

const MANAGED_PAGES = [
  { key: "overview",         label: "Overview (Dashboard)",        path: "/" },
  { key: "chat",             label: "Launch Assistant (Chat)",    path: "/assistant" },
  { key: "connections",      label: "Data Sources",               path: "/connections" },
  { key: "schema",           label: "Schema Discovery",           path: "/schema" },
  { key: "semantic",         label: "Semantic Layer",             path: "/semantic" },
  { key: "providers",        label: "AI Providers",               path: "/providers" },
  { key: "prompts",          label: "Prompt Studio",              path: "/prompts" },
  { key: "intents",          label: "Intent Configuration",       path: "/intents" },
  { key: "users",            label: "User Management",            path: "/users" },
  { key: "roles",            label: "Role Management",            path: "/roles" },
  { key: "audit",            label: "Monitoring & Audit",         path: "/audit" },
];

const DEFAULT_DIVISIONS = ["Sales", "Manufacturing", "Textiles", "Retail", "Executive"];
const DEFAULT_REGIONS = ["South", "North", "East", "West", "Central"];
const DEFAULT_PRODUCTS = ["Apparel", "Innerwear", "Accessories", "Footwear"];
const DEFAULT_CHANNELS = ["Showroom", "Wholesale", "Online", "Retail Outlet"];

export default function AccessControlMatrixModal({
  visible,
  onClose,
  API,
  token,
  roles = [],
  users = []
}) {
  const [activeTab, setActiveTab] = useState("roles");
  const [selectedRoleId, setSelectedRoleId] = useState(roles[0]?.id || null);
  const [selectedUserId, setSelectedUserId] = useState(users[0]?.id || null);

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  // Matrix State
  const [pageAccess, setPageAccess] = useState({});
  const [chatAccess, setChatAccess] = useState({ a: true, h: true, d: false });
  const [dataScope, setDataScope] = useState({
    DIVISION: [],
    REGION: [],
    PRODUCT: [],
    CHANNEL: []
  });

  // Sync initial selection
  useEffect(() => {
    if (roles.length > 0 && !selectedRoleId) {
      setSelectedRoleId(roles[0].id);
    }
    if (users.length > 0 && !selectedUserId) {
      setSelectedUserId(users[0].id);
    }
  }, [roles, users]);

  // Load matrix on tab/selection change
  useEffect(() => {
    if (!visible) return;
    if (activeTab === "roles" && selectedRoleId) {
      fetchRoleMatrix(selectedRoleId);
    } else if (activeTab === "users" && selectedUserId) {
      const u = users.find(usr => usr.id === selectedUserId);
      if (u && u.employee_id) {
        fetchUserMatrix(u.employee_id);
      }
    }
  }, [visible, selectedRoleId, selectedUserId, activeTab, users]);

  const fetchRoleMatrix = async (roleId) => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/roles/${roleId}/matrix`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setPageAccess(data.page_access || {});
        setChatAccess(data.chat_access || { a: true, h: true, d: false });
        setDataScope(data.data_scope || { DIVISION: [], REGION: [], PRODUCT: [], CHANNEL: [] });
      }
    } catch (e) {
      console.error("Failed to load role access matrix", e);
    } finally {
      setLoading(false);
    }
  };

  const fetchUserMatrix = async (employeeId) => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/admin/users/${employeeId}/matrix`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setPageAccess(data.page_overrides || {});
        setChatAccess(data.chat_overrides || { a: true, h: true, d: false });
        setDataScope(data.data_scope || { DIVISION: [], REGION: [], PRODUCT: [], CHANNEL: [] });
      }
    } catch (e) {
      console.error("Failed to load user access matrix", e);
    } finally {
      setLoading(false);
    }
  };

  const handlePageAccessChange = (pageKey, type, checked) => {
    setPageAccess(prev => ({
      ...prev,
      [pageKey]: {
        ...prev[pageKey],
        [type]: checked
      }
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      let endpoint = "";
      let payload = {
        data_scope: dataScope
      };

      if (activeTab === "roles") {
        if (!selectedRoleId) return;
        endpoint = `${API}/roles/${selectedRoleId}/matrix`;
        payload.page_access = pageAccess;
        payload.chat_access = chatAccess;
      } else {
        const u = users.find(usr => usr.id === selectedUserId);
        if (!u || !u.employee_id) {
          message.error("Selected user does not have a valid employee ID");
          return;
        }
        endpoint = `${API}/admin/users/${u.employee_id}/matrix`;
        payload.page_overrides = pageAccess;
        payload.chat_overrides = chatAccess;
      }

      const res = await fetch(endpoint, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        message.success(`Access Control Matrix saved successfully for ${activeTab === "roles" ? "role" : "user"}`);
        onClose();
      } else {
        const err = await res.json().catch(() => ({}));
        message.error(err.detail || "Failed to save Access Control Matrix");
      }
    } catch (e) {
      message.error("Failed to update access matrix");
    } finally {
      setSaving(false);
    }
  };

  const pageColumns = [
    {
      title: "Page / Module Name",
      dataIndex: "label",
      key: "label",
      render: (text, record) => (
        <Space>
          <Text strong style={{ color: "var(--text-main)" }}>{text}</Text>
          <Tag bordered={false} style={{ fontSize: "11px", color: "var(--text-muted)" }}>{record.path}</Tag>
        </Space>
      )
    },
    {
      title: "View (V)",
      key: "view",
      width: 140,
      align: "center",
      render: (_, record) => {
        const isChecked = !!pageAccess[record.key]?.v;
        return (
          <Checkbox
            checked={isChecked}
            onChange={(e) => handlePageAccessChange(record.key, "v", e.target.checked)}
          >
            <Space size={4}>
              <Eye size={14} style={{ color: isChecked ? "#10b981" : "var(--text-muted)" }} />
              <span>V</span>
            </Space>
          </Checkbox>
        );
      }
    },
    {
      title: "Modify (M)",
      key: "modify",
      width: 140,
      align: "center",
      render: (_, record) => {
        const isChecked = !!pageAccess[record.key]?.m;
        return (
          <Checkbox
            checked={isChecked}
            onChange={(e) => handlePageAccessChange(record.key, "m", e.target.checked)}
          >
            <Space size={4}>
              <Edit3 size={14} style={{ color: isChecked ? "#6366f1" : "var(--text-muted)" }} />
              <span>M</span>
            </Space>
          </Checkbox>
        );
      }
    }
  ];

  return (
    <Modal
      title={
        <Space>
          <Shield size={20} style={{ color: "#6366f1" }} />
          <span style={{ color: "var(--text-main)", fontWeight: 700 }}>Access Control & RBAC Settings</span>
        </Space>
      }
      open={visible}
      onCancel={onClose}
      width={840}
      footer={[
        <Button key="cancel" onClick={onClose}>Cancel</Button>,
        <Button key="save" type="primary" loading={saving} onClick={handleSave} style={{ background: "#4f46e5" }}>
          Save Access Matrix
        </Button>
      ]}
      styles={{ body: { padding: "20px 24px" } }}
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          { key: "roles", label: <Space><Shield size={16} /><span>By Roles</span></Space> },
          { key: "users", label: <Space><Users size={16} /><span>By Users</span></Space> }
        ]}
      />

      {activeTab === "roles" ? (
        <Card style={{ marginBottom: "20px", background: "var(--bg-card-inner)", border: "1px solid var(--border-color)" }}>
          <Space align="center" style={{ width: "100%", justifyContent: "space-between" }}>
            <Text strong style={{ color: "var(--text-main)" }}>Select Target Role:</Text>
            <Select
              value={selectedRoleId}
              onChange={setSelectedRoleId}
              style={{ width: 280 }}
            >
              {roles.map(r => (
                <Option key={r.id} value={r.id}>{r.role_name} {r.role_name === "SUPER_ADMIN" ? "(System Full Access)" : ""}</Option>
              ))}
            </Select>
          </Space>
        </Card>
      ) : (
        <Card style={{ marginBottom: "20px", background: "var(--bg-card-inner)", border: "1px solid var(--border-color)" }}>
          <Space align="center" style={{ width: "100%", justifyContent: "space-between" }}>
            <Text strong style={{ color: "var(--text-main)" }}>Select Target User:</Text>
            <Select
              value={selectedUserId}
              onChange={setSelectedUserId}
              style={{ width: 280 }}
            >
              {users.map(u => (
                <Option key={u.id} value={u.id}>{u.full_name || u.official_email} ({u.role || "User"})</Option>
              ))}
            </Select>
          </Space>
        </Card>
      )}

      {loading ? (
        <div style={{ padding: "40px", textAlign: "center" }}><Spin size="large" /></div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          {/* 1. Page Access (V/M) */}
          <div>
            <Title level={5} style={{ color: "var(--text-main)", marginBottom: "12px" }}>
              1. PAGE ACCESS (V = View, M = Modify)
            </Title>
            <Table
              dataSource={MANAGED_PAGES}
              columns={pageColumns}
              pagination={false}
              size="small"
              rowKey="key"
              style={{ border: "1px solid var(--border-color)", borderRadius: "8px" }}
            />
          </div>

          <Divider style={{ margin: 0 }} />

          {/* 2. Chat Access (A/H/D) */}
          <div>
            <Title level={5} style={{ color: "var(--text-main)", marginBottom: "12px" }}>
              2. CHAT ACCESS (A = Ask, H = History, D = Delete)
            </Title>
            <Card style={{ background: "var(--bg-card-inner)", border: "1px solid var(--border-color)" }}>
              <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <Space>
                    <MessageSquare size={16} style={{ color: "#6366f1" }} />
                    <div>
                      <Text strong style={{ color: "var(--text-main)", display: "block" }}>Ask (A) — Send Chatbot Queries</Text>
                      <Text style={{ fontSize: "12px", color: "var(--text-muted)" }}>Allows user to submit analytical questions to chatbot</Text>
                    </div>
                  </Space>
                  <Switch
                    checked={chatAccess.a}
                    onChange={(checked) => setChatAccess(prev => ({ ...prev, a: checked }))}
                  />
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <Space>
                    <Database size={16} style={{ color: "#10b981" }} />
                    <div>
                      <Text strong style={{ color: "var(--text-main)", display: "block" }}>History (H) — View Chat Sessions & Messages</Text>
                      <Text style={{ fontSize: "12px", color: "var(--text-muted)" }}>Allows user to view past chat history within authorized scope</Text>
                    </div>
                  </Space>
                  <Switch
                    checked={chatAccess.h}
                    onChange={(checked) => setChatAccess(prev => ({ ...prev, h: checked }))}
                  />
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <Space>
                    <Lock size={16} style={{ color: "#ef4444" }} />
                    <div>
                      <Text strong style={{ color: "var(--text-main)", display: "block" }}>Delete (D) — Delete Chat Sessions</Text>
                      <Text style={{ fontSize: "12px", color: "var(--text-muted)" }}>Allows user to permanently delete chat sessions</Text>
                    </div>
                  </Space>
                  <Switch
                    checked={chatAccess.d}
                    onChange={(checked) => setChatAccess(prev => ({ ...prev, d: checked }))}
                  />
                </div>
              </Space>
            </Card>
          </div>

          <Divider style={{ margin: 0 }} />

          {/* 3. Data Scope Dimensions */}
          <div>
            <Title level={5} style={{ color: "var(--text-main)", marginBottom: "12px" }}>
              3. DATA SCOPE (BUSINESS DIMENSIONS)
            </Title>
            <Card style={{ background: "var(--bg-card-inner)", border: "1px solid var(--border-color)" }}>
              <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                {/* Division */}
                <div>
                  <Text strong style={{ color: "var(--text-main)", display: "block", marginBottom: "6px" }}>
                    <Layers size={14} style={{ marginRight: 6, color: "#6366f1" }} />
                    Division Scope
                  </Text>
                  <Select
                    mode="tags"
                    placeholder="Select authorized Divisions (e.g. Sales, Manufacturing)"
                    value={dataScope.DIVISION || []}
                    onChange={(vals) => setDataScope(prev => ({ ...prev, DIVISION: vals }))}
                    style={{ width: "100%" }}
                  >
                    {DEFAULT_DIVISIONS.map(d => <Option key={d} value={d}>{d}</Option>)}
                  </Select>
                </div>

                {/* Region */}
                <div>
                  <Text strong style={{ color: "var(--text-main)", display: "block", marginBottom: "6px" }}>
                    <Globe size={14} style={{ marginRight: 6, color: "#10b981" }} />
                    Region Scope
                  </Text>
                  <Select
                    mode="tags"
                    placeholder="Select authorized Regions (e.g. South, North)"
                    value={dataScope.REGION || []}
                    onChange={(vals) => setDataScope(prev => ({ ...prev, REGION: vals }))}
                    style={{ width: "100%" }}
                  >
                    {DEFAULT_REGIONS.map(r => <Option key={r} value={r}>{r}</Option>)}
                  </Select>
                </div>

                {/* Product */}
                <div>
                  <Text strong style={{ color: "var(--text-main)", display: "block", marginBottom: "6px" }}>
                    <Package size={14} style={{ marginRight: 6, color: "#f59e0b" }} />
                    Product Scope
                  </Text>
                  <Select
                    mode="tags"
                    placeholder="Select authorized Products (e.g. Apparel, Innerwear)"
                    value={dataScope.PRODUCT || []}
                    onChange={(vals) => setDataScope(prev => ({ ...prev, PRODUCT: vals }))}
                    style={{ width: "100%" }}
                  >
                    {DEFAULT_PRODUCTS.map(p => <Option key={p} value={p}>{p}</Option>)}
                  </Select>
                </div>

                {/* Channel */}
                <div>
                  <Text strong style={{ color: "var(--text-main)", display: "block", marginBottom: "6px" }}>
                    <ShoppingBag size={14} style={{ marginRight: 6, color: "#ec4899" }} />
                    Channel Scope
                  </Text>
                  <Select
                    mode="tags"
                    placeholder="Select authorized Channels (e.g. Showroom, Wholesale)"
                    value={dataScope.CHANNEL || []}
                    onChange={(vals) => setDataScope(prev => ({ ...prev, CHANNEL: vals }))}
                    style={{ width: "100%" }}
                  >
                    {DEFAULT_CHANNELS.map(c => <Option key={c} value={c}>{c}</Option>)}
                  </Select>
                </div>
              </Space>
            </Card>
          </div>
        </div>
      )}
    </Modal>
  );
}
