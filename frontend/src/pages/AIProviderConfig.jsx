import React, { useState, useEffect } from "react";
import { 
  Table, Card, Button, Tag, Space, Typography, Modal, Form, 
  Input, Select, Tabs, Divider, Row, Col, Badge, Switch,
  Tooltip, Popconfirm, List, Alert, Spin
} from "antd";
import { message } from "../utils/message";
import { 
  PlusOutlined, SettingOutlined, KeyOutlined, AppstoreOutlined, 
  NodeIndexOutlined, CheckCircleOutlined, CloseCircleOutlined,
  WarningOutlined, QuestionCircleOutlined, DeleteOutlined,
  ArrowUpOutlined, ArrowDownOutlined, EditOutlined, GlobalOutlined,
  ExperimentOutlined, DashboardOutlined
} from "@ant-design/icons";

// Runtime verification of imported components before rendering
const componentRegistry = {
  Table, Card, Button, Tag, Space, Typography, Modal, Form, 
  Input, Select, message, Tabs, Divider, Row, Col, Badge, Switch,
  Tooltip, Popconfirm, List, Alert, Spin,
  ListItem: List?.Item
};

Object.entries(componentRegistry).forEach(([name, val]) => {
  if (val === undefined) {
    console.warn(`[AIProviderConfig] Warning: ${name} component is undefined at runtime.`);
  }
});

const { Title = (() => null), Text = (() => null), Paragraph = (() => null) } = Typography || {};
const { Option = (() => null) } = Select || {};

// Safely resolve List.Item to prevent "Element type is invalid" errors
const ListItem = List?.Item || (({ children, actions, ...props }) => (
  <div {...props}>
    {children}
    {actions && <div className="ant-list-item-actions" style={{ display: "flex", gap: "8px" }}>{actions}</div>}
  </div>
));

// Helper to normalize FastAPI/Pydantic validation errors
const normalizeErrorDetail = (detail, defaultMsg) => {
  if (!detail) return defaultMsg;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const errors = detail.map(err => {
      if (err && typeof err === "object") {
        const field = Array.isArray(err.loc) ? err.loc[err.loc.length - 1] : "";
        const msg = err.msg || "Invalid value";
        return field ? `${field}: ${msg}` : msg;
      }
      return String(err);
    });
    return errors.join("; ");
  }
  if (typeof detail === "object") {
    return JSON.stringify(detail);
  }
  return String(detail);
};

// Helper to group model-purpose rows by provider_id + model_name
const groupModels = (modelsList) => {
  const groups = {};
  modelsList.forEach(m => {
    const key = `${m.provider_id}::${m.model_name}`;
    if (!groups[key]) {
      groups[key] = {
        model_id: m.model_id, // Keep the first model_id for PUT/DELETE/TEST API calls
        provider_id: m.provider_id,
        model_name: m.model_name,
        provider_name: m.provider_name,
        provider_type: m.provider_type,
        provider_active: m.provider_active,
        health_status: m.health_status,
        is_active: m.is_active,
        purposes: [],
        all_ids: []
      };
    }
    groups[key].purposes.push(m.purpose);
    groups[key].all_ids.push(m.model_id);
    if (m.is_active) {
      groups[key].is_active = true;
    }
  });
  return Object.values(groups);
};

export default function AIProviderConfig({ API, token }) {
  const [providers, setProviders] = useState([]);
  const [models, setModels] = useState([]);
  const [rawModels, setRawModels] = useState([]);
  const [fallbacks, setFallbacks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("routing");
  
  // Modals
  const [providerModalVisible, setProviderModalVisible] = useState(false);
  const [modelModalVisible, setModelModalVisible] = useState(false);
  const [keyModalVisible, setKeyModalVisible] = useState(false);
  
  const [selectedProvider, setSelectedProvider] = useState(null);
  const [selectedModel, setSelectedModel] = useState(null);
  
  // Inline loading states
  const [testingProviderId, setTestingProviderId] = useState(null);
  const [testingModelId, setTestingModelId] = useState(null);

  const [formProvider] = Form.useForm();
  const [formModel] = Form.useForm();
  const [formKey] = Form.useForm();

  // Load all configurations
  const loadData = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const [provRes, modelRes, fallbackRes] = await Promise.all([
        fetch(`${API}/providers`, { headers }),
        fetch(`${API}/models`, { headers }),
        fetch(`${API}/fallbacks`, { headers })
      ]);

      let provData = [];
      let modelData = [];
      let fallbackData = [];

      if (provRes.ok) provData = await provRes.json();
      if (modelRes.ok) modelData = await modelRes.json();
      if (fallbackRes.ok) fallbackData = await fallbackRes.json();

      setProviders(provData);
      setRawModels(modelData);
      setModels(groupModels(modelData));
      setFallbacks(fallbackData);
    } catch (err) {
      console.error(err);
      message.error("Failed to load configurations from server.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [token, API]); // eslint-disable-line

  // Generic Error Handler
  const handleRequestError = async (res, defaultMsg) => {
    try {
      const errData = await res.json();
      const errorMsg = normalizeErrorDetail(errData.detail, defaultMsg);
      message.error(errorMsg);
    } catch {
      message.error(defaultMsg);
    }
  };

  // --- Providers API calls ---
  const handleCreateProvider = async (values) => {
    try {
      const res = await fetch(`${API}/providers`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(values)
      });
      if (res.ok) {
        message.success("AI Provider registered successfully");
        setProviderModalVisible(false);
        formProvider.resetFields();
        loadData();
      } else {
        await handleRequestError(res, "Failed to create provider");
      }
    } catch (err) {
      console.error(err);
      message.error("Network error while creating provider");
    }
  };

  const handleUpdateProvider = async (values) => {
    try {
      const res = await fetch(`${API}/providers/${selectedProvider.provider_id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(values)
      });
      if (res.ok) {
        message.success("AI Provider updated successfully");
        setProviderModalVisible(false);
        setSelectedProvider(null);
        formProvider.resetFields();
        loadData();
      } else {
        await handleRequestError(res, "Failed to update provider");
      }
    } catch (err) {
      console.error(err);
      message.error("Network error while updating provider");
    }
  };

  const toggleProviderActive = async (checked, record) => {
    try {
      const res = await fetch(`${API}/providers/${record.provider_id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          provider_name: record.provider_name,
          provider_type: record.provider_type,
          base_url: record.base_url,
          is_active: checked
        })
      });
      if (res.ok) {
        message.success(`Provider "${record.provider_name}" ${checked ? "enabled" : "disabled"}`);
        loadData();
      } else {
        await handleRequestError(res, "Failed to toggle provider state");
      }
    } catch (err) {
      console.error(err);
      message.error("Network error updating provider state");
    }
  };

  const handleSaveKey = async (values) => {
    try {
      const res = await fetch(`${API}/providers/${selectedProvider.provider_id}/api-key`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ api_key: values.api_key })
      });
      if (res.ok) {
        message.success(`API key updated for "${selectedProvider.provider_name}"`);
        setKeyModalVisible(false);
        setSelectedProvider(null);
        formKey.resetFields();
        loadData();
      } else {
        await handleRequestError(res, "Failed to save API key");
      }
    } catch (err) {
      console.error(err);
      message.error("Network error updating credentials");
    }
  };

  const handleTestProvider = async (record) => {
    setTestingProviderId(record.provider_id);
    try {
      const res = await fetch(`${API}/providers/${record.provider_id}/test`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      const data = await res.json();
      if (data.status === "success") {
        message.success(`Connection successful! Latency: ${data.latency_ms}ms`);
      } else {
        message.error(`Connection failed: ${data.error || "Unknown error"}`);
      }
      loadData(); // Reload to fetch fresh health status
    } catch (err) {
      console.error(err);
      message.error("Failed to run provider connection test");
    } finally {
      setTestingProviderId(null);
    }
  };

  const handleDeleteProvider = async (record) => {
    Modal.confirm({
      title: "Delete Provider?",
      content: (
        <div>
          <p>Are you sure you want to delete <strong>{record.provider_name}</strong>?</p>
          <p style={{ color: "var(--text-muted)", fontSize: "12px" }}>This action cannot be undone and will delete all models registered for this provider.</p>
        </div>
      ),
      okText: "Delete",
      okType: "danger",
      cancelText: "Cancel",
      onOk: async () => {
        try {
          const res = await fetch(`${API}/providers/${record.provider_id}`, {
            method: "DELETE",
            headers: { Authorization: `Bearer ${token}` }
          });
          if (res.ok) {
            message.success(`Provider "${record.provider_name}" deleted successfully.`);
            loadData();
          } else {
            await handleRequestError(res, "Failed to delete provider");
          }
        } catch (err) {
          console.error(err);
          message.error("Network error while deleting provider");
        }
      }
    });
  };

  // --- Models API calls ---
  const handleCreateModel = async (values) => {
    try {
      const res = await fetch(`${API}/models`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(values)
      });
      if (res.ok) {
        message.success("Model registered successfully");
        setModelModalVisible(false);
        formModel.resetFields();
        loadData();
      } else {
        await handleRequestError(res, "Failed to register model");
      }
    } catch (err) {
      console.error(err);
      message.error("Network error creating model");
    }
  };

  const handleUpdateModel = async (values) => {
    try {
      const payload = {
        ...values,
        is_active: values.is_active !== undefined ? values.is_active : (selectedModel ? selectedModel.is_active : true)
      };
      const res = await fetch(`${API}/models/${selectedModel.model_id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        message.success("Model registration updated");
        setModelModalVisible(false);
        setSelectedModel(null);
        formModel.resetFields();
        loadData();
      } else {
        await handleRequestError(res, "Failed to update model");
      }
    } catch (err) {
      console.error(err);
      message.error("Network error updating model");
    }
  };

  const toggleModelActive = async (checked, record) => {
    try {
      const res = await fetch(`${API}/models/${record.model_id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          model_name: record.model_name,
          purposes: record.purposes,
          is_active: checked
        })
      });
      if (res.ok) {
        message.success(`Model "${record.model_name}" ${checked ? "enabled" : "disabled"}`);
        loadData();
      } else {
        await handleRequestError(res, "Failed to update model status");
      }
    } catch (err) {
      console.error(err);
      message.error("Network error updating model status");
    }
  };

  const handleTestModel = async (record) => {
    setTestingModelId(record.model_id);
    try {
      const res = await fetch(`${API}/models/${record.model_id}/test`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      const data = await res.json();
      if (data.status === "success") {
        message.success(`Model test passed! Latency: ${data.latency_ms}ms`);
      } else {
        message.error(`Model test failed: ${data.error || "Unknown error"}`);
      }
      loadData();
    } catch (err) {
      console.error(err);
      message.error("Network error running model connection test");
    } finally {
      setTestingModelId(null);
    }
  };

  const handleDeleteModel = async (record) => {
    Modal.confirm({
      title: "Delete Model?",
      content: (
        <div>
          <p>Are you sure you want to delete <strong>{record.model_name}</strong>?</p>
          <p style={{ color: "var(--text-muted)", fontSize: "12px" }}>This action cannot be undone.</p>
        </div>
      ),
      okText: "Delete",
      okType: "danger",
      cancelText: "Cancel",
      onOk: async () => {
        try {
          const res = await fetch(`${API}/models/${record.model_id}`, {
            method: "DELETE",
            headers: { Authorization: `Bearer ${token}` }
          });
          if (res.ok) {
            message.success(`Model "${record.model_name}" deleted successfully.`);
            loadData();
          } else {
            await handleRequestError(res, "Failed to delete model");
          }
        } catch (err) {
          console.error(err);
          message.error("Network error while deleting model");
        }
      }
    });
  };

  // --- Routing & Fallbacks API calls ---
  const handleSetPrimary = async (purpose, modelId) => {
    try {
      const res = await fetch(`${API}/model-routing`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ purpose, model_id: modelId })
      });
      if (res.ok) {
        message.success(`Primary model updated for ${purpose}`);
        loadData();
      } else {
        await handleRequestError(res, "Failed to update primary routing");
      }
    } catch (err) {
      console.error(err);
      message.error("Network error updating routing");
    }
  };

  const handleAddFallback = async (purpose, modelId) => {
    if (!modelId) return;
    try {
      const res = await fetch(`${API}/fallbacks`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ purpose, model_id: modelId })
      });
      if (res.ok) {
        message.success("Fallback model appended to list");
        loadData();
      } else {
        await handleRequestError(res, "Failed to add fallback");
      }
    } catch (err) {
      console.error(err);
      message.error("Network error adding fallback");
    }
  };

  const handleRemoveFallback = async (fallbackId) => {
    try {
      const res = await fetch(`${API}/fallbacks/${fallbackId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        message.success("Fallback route removed");
        loadData();
      } else {
        await handleRequestError(res, "Failed to remove fallback");
      }
    } catch (err) {
      console.error(err);
      message.error("Network error removing fallback");
    }
  };

  const handleReorder = async (purpose, fallbackItems, index, direction) => {
    const updated = [...fallbackItems];
    const targetIdx = direction === "up" ? index - 1 : index + 1;
    if (targetIdx < 0 || targetIdx >= updated.length) return;
    
    // Swap
    const temp = updated[index];
    updated[index] = updated[targetIdx];
    updated[targetIdx] = temp;

    const orderedIds = updated.map(f => f.fallback_id);
    try {
      const res = await fetch(`${API}/fallbacks/reorder`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          purpose,
          ordered_fallback_ids: orderedIds
        })
      });
      if (res.ok) {
        message.success("Fallback priorities updated");
        loadData();
      } else {
        await handleRequestError(res, "Failed to reorder fallbacks");
      }
    } catch (err) {
      console.error(err);
      message.error("Network error reordering fallbacks");
    }
  };

  // --- Health badge helper ---
  const renderHealthBadge = (isActive, status, lastError = "") => {
    if (!isActive) return <Tag color="default">DISABLED</Tag>;
    switch (status) {
      case "HEALTHY":
        return <Tag color="success" icon={<CheckCircleOutlined />}>CONNECTED</Tag>;
      case "FAILED":
        if (lastError && lastError.toLowerCase().includes("timeout")) {
          return (
            <Tooltip title={lastError}>
              <Tag color="warning" icon={<WarningOutlined />}>TIMEOUT</Tag>
            </Tooltip>
          );
        }
        return (
          <Tooltip title={lastError}>
            <Tag color="error" icon={<CloseCircleOutlined />}>FAILED</Tag>
          </Tooltip>
        );
      case "UNKNOWN":
      default:
        return <Tag color="blue" icon={<QuestionCircleOutlined />}>UNKNOWN</Tag>;
    }
  };

  // Render stats summary cards
  const activeProvidersCount = providers.filter(p => p.is_active).length;
  const activeModelsCount = models.filter(m => m.is_active).length;
  const healthyCount = providers.filter(p => p.is_active && p.status === "HEALTHY").length;
  const fallbackRoutesCount = fallbacks.length;

  const renderOverviewHeader = () => (
    <Row gutter={[16, 16]} style={{ marginBottom: "24px" }}>
      <Col xs={24} sm={12} md={6}>
        <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "10px" }} styles={{ body: { padding: "16px" } }}>
          <Space align="baseline">
            <DashboardOutlined style={{ fontSize: "20px", color: "#4f46e5" }} />
            <div>
              <Text type="secondary" style={{ fontSize: "12px", display: "block" }}>Active Providers</Text>
              <Text strong style={{ fontSize: "22px", color: "var(--text-main)" }}>{activeProvidersCount} / {providers.length}</Text>
            </div>
          </Space>
        </Card>
      </Col>
      <Col xs={24} sm={12} md={6}>
        <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "10px" }} styles={{ body: { padding: "16px" } }}>
          <Space align="baseline">
            <AppstoreOutlined style={{ fontSize: "20px", color: "#10b981" }} />
            <div>
              <Text type="secondary" style={{ fontSize: "12px", display: "block" }}>Registered Models</Text>
              <Text strong style={{ fontSize: "22px", color: "var(--text-main)" }}>{activeModelsCount} / {models.length}</Text>
            </div>
          </Space>
        </Card>
      </Col>
      <Col xs={24} sm={12} md={6}>
        <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "10px" }} styles={{ body: { padding: "16px" } }}>
          <Space align="baseline">
            <CheckCircleOutlined style={{ fontSize: "20px", color: "#10b981" }} />
            <div>
              <Text type="secondary" style={{ fontSize: "12px", display: "block" }}>Healthy Connections</Text>
              <Text strong style={{ fontSize: "22px", color: "var(--text-main)" }}>{healthyCount} Healthy</Text>
            </div>
          </Space>
        </Card>
      </Col>
      <Col xs={24} sm={12} md={6}>
        <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "10px" }} styles={{ body: { padding: "16px" } }}>
          <Space align="baseline">
            <NodeIndexOutlined style={{ fontSize: "20px", color: "#8b5cf6" }} />
            <div>
              <Text type="secondary" style={{ fontSize: "12px", display: "block" }}>Fallback Routes</Text>
              <Text strong style={{ fontSize: "22px", color: "var(--text-main)" }}>{fallbackRoutesCount} Configured</Text>
            </div>
          </Space>
        </Card>
      </Col>
    </Row>
  );

  // Table Columns config
  const providerColumns = [
    {
      title: "Provider Name",
      dataIndex: "provider_name",
      key: "provider_name",
      render: (text) => <span style={{ fontWeight: 600, color: "var(--text-main)" }}>{text}</span>
    },
    {
      title: "Type",
      dataIndex: "provider_type",
      key: "provider_type",
      render: (text) => <Tag color="indigo">{text.toUpperCase()}</Tag>
    },
    {
      title: "Base URL Endpoint",
      dataIndex: "base_url",
      key: "base_url",
      render: (text) => <code style={{ color: "var(--text-muted)", fontSize: "11px" }}>{text || "Default Server Endpoint"}</code>
    },
    {
      title: "Health Status",
      key: "status",
      render: (_, record) => renderHealthBadge(record.is_active, record.status, record.last_error)
    },
    {
      title: "Telemetry (Latency)",
      key: "telemetry",
      render: (_, record) => {
        if (!record.is_active || record.status === "UNKNOWN") return <Text type="secondary">-</Text>;
        
        const statusText = record.status === "HEALTHY" ? "CONNECTED" : (record.last_error?.toLowerCase().includes("timeout") ? "TIMEOUT" : "FAILED");
        const statusColor = record.status === "HEALTHY" ? "#10b981" : "#ef4444";
        
        return (
          <div style={{ fontSize: "12px", lineHeight: "1.4" }}>
            {record.average_response_ms ? (
              <div style={{ color: "#10b981", fontWeight: 500, marginBottom: "4px" }}>{Math.round(record.average_response_ms)} ms avg</div>
            ) : (
              <div style={{ color: "var(--text-muted)", marginBottom: "4px" }}>Pending test</div>
            )}
            <div style={{ fontSize: "10px", color: "var(--text-muted)" }}>
              <div style={{ fontWeight: 600, color: statusColor, textTransform: "uppercase", marginBottom: "2px" }}>{statusText}</div>
              <div>Consecutive Failures: <span style={{ color: record.consecutive_failures > 0 ? "#ef4444" : "inherit" }}>{record.consecutive_failures ?? 0}</span></div>
              <div>Total Failures: <span>{record.failure_count ?? 0}</span></div>
              {record.last_success_at && (
                <div>Last Success: <span style={{ fontSize: "9px" }}>{new Date(record.last_success_at).toLocaleString()}</span></div>
              )}
            </div>
          </div>
        );
      }
    },
    {
      title: "API Key",
      key: "api_key",
      render: (_, record) => (
        <Space>
          {record.masked_api_key ? (
            <Tooltip title="Securely Encrypted">
              <Tag color="success"><KeyOutlined /> {record.masked_api_key}</Tag>
            </Tooltip>
          ) : (
            <Tag color="warning">NO KEY SET</Tag>
          )}
          <Button 
            type="text" 
            size="small"
            icon={<KeyOutlined />} 
            onClick={() => {
              setSelectedProvider(record);
              setKeyModalVisible(true);
            }}
            data-testid={`key-btn-${record.provider_id}`}
          />
        </Space>
      )
    },
    {
      title: "Enabled",
      dataIndex: "is_active",
      key: "is_active",
      render: (isActive, record) => (
        <Switch 
          checked={isActive} 
          size="small"
          onChange={(checked) => toggleProviderActive(checked, record)} 
        />
      )
    },
    {
      title: "Actions",
      key: "actions",
      render: (_, record) => (
        <Space>
          <Button 
            type="primary"
            size="small"
            ghost
            onClick={() => {
              setSelectedProvider(record);
              formProvider.setFieldsValue({
                provider_name: record.provider_name,
                provider_type: record.provider_type,
                base_url: record.base_url,
                is_active: record.is_active
              });
              setProviderModalVisible(true);
            }}
            icon={<EditOutlined />}
          >
            Edit
          </Button>
          <Button 
            type="default" 
            size="small"
            loading={testingProviderId === record.provider_id}
            disabled={!record.is_active}
            onClick={() => handleTestProvider(record)}
            icon={<GlobalOutlined />}
          >
            Test Connection
          </Button>
          <Button 
            type="text" 
            danger 
            icon={<DeleteOutlined />}
            onClick={() => handleDeleteProvider(record)}
            title="Delete Provider"
          >
            Delete
          </Button>
        </Space>
      )
    }
  ];

  const modelColumns = [
    {
      title: "Model Name / ID",
      dataIndex: "model_name",
      key: "model_name",
      render: (text) => <span style={{ fontFamily: "monospace", fontWeight: 600, color: "var(--text-main)" }}>{text}</span>
    },
    {
      title: "Provider",
      dataIndex: "provider_name",
      key: "provider_name",
      render: (text) => <Tag color="blue">{text}</Tag>
    },
    {
      title: "Capabilities / Workloads",
      dataIndex: "purposes",
      key: "purposes",
      render: (purposes) => (
        <Space size={[4, 4]} wrap>
          {(purposes || []).map(text => {
            let color = "purple";
            let friendlyLabel = text.toUpperCase();
            if (text === "sql_generation") { color = "geekblue"; friendlyLabel = "SQL Generation"; }
            if (text === "insight") { color = "cyan"; friendlyLabel = "Business Insight"; }
            if (text === "chart") { color = "orange"; friendlyLabel = "Chart / Viz"; }
            if (text === "intent") { color = "purple"; friendlyLabel = "Intent"; }
            return <Tag color={color} key={text}>{friendlyLabel}</Tag>;
          })}
        </Space>
      )
    },
    {
      title: "Health",
      key: "health",
      render: (_, record) => renderHealthBadge(record.provider_active && record.is_active, record.health_status)
    },
    {
      title: "Active",
      dataIndex: "is_active",
      key: "is_active",
      render: (isActive, record) => (
        <Switch 
          checked={isActive}
          size="small"
          onChange={(checked) => toggleModelActive(checked, record)}
        />
      )
    },
    {
      title: "Actions",
      key: "actions",
      render: (_, record) => (
        <Space>
          <Button 
            type="primary"
            size="small"
            ghost
            onClick={() => {
              setSelectedModel(record);
              formModel.setFieldsValue({
                provider_id: record.provider_id,
                model_name: record.model_name,
                purposes: record.purposes,
                is_active: record.is_active
              });
              setModelModalVisible(true);
            }}
            icon={<EditOutlined />}
          >
            Edit
          </Button>
          <Button 
            type="default" 
            size="small"
            loading={testingModelId === record.model_id}
            disabled={!record.is_active || !record.provider_active}
            onClick={() => handleTestModel(record)}
            icon={<ExperimentOutlined />}
          >
            Test Model
          </Button>
          <Button 
            type="text" 
            danger 
            icon={<DeleteOutlined />}
            onClick={() => handleDeleteModel(record)}
            title="Delete Model"
          >
            Delete
          </Button>
        </Space>
      )
    }
  ];

  // Routing render helpers
  const renderFallbackList = (purpose, purposeFallbacks, purposeModels) => {
    if (purposeFallbacks.length === 0) {
      return <Alert message="No fallback models configured for this workload purpose. Requests will fail if the primary model goes offline." type="warning" showIcon style={{ padding: "8px 16px", borderRadius: "8px" }} />;
    }
    return (
      <List
        size="small"
        bordered
        dataSource={purposeFallbacks}
        renderItem={(item, index) => (
          <ListItem
            actions={[
              <Space key="actions">
                <Button 
                  size="small"
                  type="text"
                  disabled={index === 0}
                  icon={<ArrowUpOutlined />}
                  onClick={() => handleReorder(purpose, purposeFallbacks, index, "up")}
                />
                <Button 
                  size="small"
                  type="text"
                  disabled={index === purposeFallbacks.length - 1}
                  icon={<ArrowDownOutlined />}
                  onClick={() => handleReorder(purpose, purposeFallbacks, index, "down")}
                />
                <Popconfirm
                  title="Remove this model from fallbacks?"
                  onConfirm={() => handleRemoveFallback(item.fallback_id)}
                  okText="Yes"
                  cancelText="No"
                >
                  <Button 
                    size="small"
                    danger
                    type="text"
                    icon={<DeleteOutlined />}
                    aria-label="Delete fallback"
                  />
                </Popconfirm>
              </Space>
            ]}
            style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
          >
            <div>
              <Text strong style={{ marginRight: "12px", color: "var(--text-muted)" }}>#{index + 1}</Text>
              <Text style={{ fontFamily: "monospace" }}>{item.model_name}</Text>
              <Tag style={{ marginLeft: "8px" }} color="blue">{item.provider_name}</Tag>
            </div>
          </ListItem>
        )}
        style={{ borderRadius: "8px", background: "var(--bg-card)" }}
      />
    );
  };

  const renderPurposeRoutingCard = (title, desc, purpose) => {
    // Get fallbacks for this purpose
    const purposeFallbacks = fallbacks.filter(f => f.purpose === purpose);
    
    // Available models registered under this purpose and active
    const purposeModels = rawModels.filter(m => m.purpose === purpose && m.is_active && m.provider_active);
    
    // Find primary model from fallback with priority_order = 1
    const primaryFallback = purposeFallbacks.find(f => f.priority_order === 1);
    const primaryModelId = primaryFallback ? primaryFallback.model_id : "";

    // Models that are not already primary or fallbacks
    const usedModelIds = purposeFallbacks.map(f => f.model_id);
    const availableFallbacks = purposeModels.filter(m => !usedModelIds.includes(m.model_id));

    return (
      <Card 
        title={<span style={{ color: "var(--text-main)" }}>{title}</span>} 
        bordered={false} 
        style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "10px", height: "100%" }}
      >
        <Paragraph style={{ color: "var(--text-muted)", fontSize: "13px" }}>{desc}</Paragraph>
        <Divider style={{ margin: "12px 0" }} />
        
        {/* Primary selection */}
        <div style={{ marginBottom: "18px" }}>
          <Text strong style={{ display: "block", marginBottom: "8px", color: "var(--text-secondary)" }}>PRIMARY MODEL ROUTE</Text>
          <Select 
            value={primaryModelId || undefined}
            placeholder="Select primary model route"
            onChange={(val) => handleSetPrimary(purpose, val)}
            style={{ width: "100%" }}
          >
            {purposeModels.map(m => (
              <Option key={m.model_id} value={m.model_id}>{m.model_name} ({m.provider_name})</Option>
            ))}
          </Select>
        </div>

        {/* Fallbacks queue */}
        <div style={{ marginBottom: "18px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <Text strong style={{ color: "var(--text-secondary)" }}>FAILOVER FALLBACK CHAIN</Text>
            {availableFallbacks.length > 0 && (
              <Select
                placeholder="+ Add Fallback Model"
                size="small"
                onChange={(val) => handleAddFallback(purpose, val)}
                value={null}
                style={{ width: "160px" }}
              >
                {availableFallbacks.map(m => (
                  <Option key={m.model_id} value={m.model_id}>{m.model_name}</Option>
                ))}
              </Select>
            )}
          </div>
          {renderFallbackList(purpose, purposeFallbacks.filter(f => f.priority_order > 1), purposeModels)}
        </div>
      </Card>
    );
  };

  return (
    <div style={{ padding: "4px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
        <div>
          <Title level={3} style={{ color: "var(--text-main)", margin: 0, fontWeight: 700 }}>
            AI Model Control Center
          </Title>
          <Text style={{ color: "var(--text-muted)" }}>
            Configure and test AI connection nodes, manage API credentials, and organize active model failover routing.
          </Text>
        </div>
        <Space>
          {activeTab === "providers" && (
            <Button 
              type="primary" 
              icon={<PlusOutlined />}
              style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}
              onClick={() => {
                setSelectedProvider(null);
                formProvider.resetFields();
                setProviderModalVisible(true);
              }}
            >
              Add Provider
            </Button>
          )}
          {activeTab === "models" && (
            <Button 
              type="primary" 
              icon={<PlusOutlined />}
              style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}
              onClick={() => {
                setSelectedModel(null);
                formModel.resetFields();
                formModel.setFieldsValue({ is_active: true });
                setModelModalVisible(true);
              }}
            >
              Add Model
            </Button>
          )}
        </Space>
      </div>

      {renderOverviewHeader()}

      <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px" }}>
        <Tabs 
          activeKey={activeTab} 
          onChange={setActiveTab}
          items={[
            {
              key: "routing",
              label: <span style={{ color: "var(--text-main)" }}><NodeIndexOutlined /> Routing & Fallbacks</span>,
              children: (
                <div style={{ padding: "8px 0" }}>
                  {loading ? (
                    <div style={{ textAlign: "center", padding: "40px" }}><Spin size="large" /></div>
                  ) : (
                    <Row gutter={[16, 16]}>
                      <Col xs={24} md={12}>
                        {renderPurposeRoutingCard(
                          "SQL Query Generation", 
                          "Parses user questions into structured T-SQL database queries.", 
                          "sql_generation"
                        )}
                      </Col>
                      <Col xs={24} md={12}>
                        {renderPurposeRoutingCard(
                          "Business Explanation & Insights", 
                          "Explains analytical results, trends, and aggregates in professional business terminology.", 
                          "insight"
                        )}
                      </Col>
                      <Col xs={24} md={12}>
                        {renderPurposeRoutingCard(
                          "Conversational Intent Classifier", 
                          "Differentiates between direct database search intents and normal conversation chats.", 
                          "intent"
                        )}
                      </Col>
                      <Col xs={24} md={12}>
                        {renderPurposeRoutingCard(
                          "Chart Aggregator & Visual Selector", 
                          "Decides which visual graph structures are appropriate for rendering database rows.", 
                          "chart"
                        )}
                      </Col>
                    </Row>
                  )}
                </div>
              )
            },
            {
              key: "providers",
              label: <span style={{ color: "var(--text-main)" }}><SettingOutlined /> Connection Providers</span>,
              children: (
                <Table 
                  dataSource={providers} 
                  columns={providerColumns} 
                  loading={loading}
                  pagination={false}
                  rowKey="provider_id"
                  style={{ background: "var(--bg-card)" }}
                  className="dark-table"
                />
              )
            },
            {
              key: "models",
              label: <span style={{ color: "var(--text-main)" }}><AppstoreOutlined /> Registered Models</span>,
              children: (
                <Table 
                  dataSource={models} 
                  columns={modelColumns} 
                  loading={loading}
                  pagination={false}
                  rowKey="model_id"
                  style={{ background: "var(--bg-card)" }}
                  className="dark-table"
                />
              )
            }
          ]}
        />
      </Card>

      {/* Provider Add/Edit Modal */}
      <Modal
        title={<span style={{ color: "var(--text-main)" }}>{selectedProvider ? "Modify Provider Reference" : "Register AI Connection Node"}</span>}
        open={providerModalVisible}
        onCancel={() => setProviderModalVisible(false)}
        footer={null}
        styles={{ body: { backgroundColor: "var(--bg-card)", padding: "16px 24px" } }}
      >
        <Form form={formProvider} layout="vertical" onFinish={selectedProvider ? handleUpdateProvider : handleCreateProvider}>
          <Form.Item
            name="provider_name"
            label={<span style={{ color: "var(--text-secondary)" }}>Provider Reference Name</span>}
            rules={[{ required: true, message: "Please enter a reference name" }]}
          >
            <Input placeholder="e.g. OpenAI Cloud Production" />
          </Form.Item>
          <Form.Item
            name="provider_type"
            label={<span style={{ color: "var(--text-secondary)" }}>Connection Protocol / Platform</span>}
            rules={[{ required: true, message: "Please select a provider type" }]}
          >
            <Select placeholder="Select type">
              <Option value="openai">OpenAI (Official)</Option>
              <Option value="nvidia">Nvidia API Gateway</Option>
              <Option value="groq">Groq Cloud Platform</Option>
              <Option value="openrouter">OpenRouter Server</Option>
              <Option value="custom_openai">Custom OpenAI-Compatible Protocol</Option>
              <Option value="ollama">Ollama Local Engine</Option>
            </Select>
          </Form.Item>
          <Form.Item
            name="base_url"
            label={<span style={{ color: "var(--text-secondary)" }}>Base Endpoint URL</span>}
          >
            <Input placeholder="e.g. https://api.openai.com/v1" />
          </Form.Item>
          
          {!selectedProvider && (
            <Form.Item
              name="api_key"
              label={<span style={{ color: "var(--text-secondary)" }}>Access Token API Key</span>}
              rules={[{ required: true, message: "API credentials are required during registration" }]}
            >
              <Input.Password placeholder="sk-••••••••••••••••••••••••" />
            </Form.Item>
          )}

          <Form.Item style={{ margin: 0, marginTop: "24px", textAlign: "right" }}>
            <Space>
              <Button onClick={() => setProviderModalVisible(false)}>Cancel</Button>
              <Button type="primary" htmlType="submit" style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}>
                Save Node Config
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Model Add/Edit Modal */}
      <Modal
        title={<span style={{ color: "var(--text-main)" }}>{selectedModel ? "Modify Model Definition" : "Register Model Reference"}</span>}
        open={modelModalVisible}
        onCancel={() => setModelModalVisible(false)}
        footer={null}
        styles={{ body: { backgroundColor: "var(--bg-card)", padding: "16px 24px" } }}
      >
        <Form form={formModel} layout="vertical" onFinish={selectedModel ? handleUpdateModel : handleCreateModel}>
          {!selectedModel && (
            <Form.Item
              name="provider_id"
              label={<span style={{ color: "var(--text-secondary)" }}>Target Connection Provider</span>}
              rules={[{ required: true, message: "Please associate this model with a provider" }]}
            >
              <Select placeholder="Select provider node">
                {providers.map(p => (
                  <Option key={p.provider_id} value={p.provider_id}>{p.provider_name}</Option>
                ))}
              </Select>
            </Form.Item>
          )}
          <Form.Item
            name="model_name"
            label={<span style={{ color: "var(--text-secondary)" }}>Model Technical Identifier</span>}
            rules={[{ required: true, message: "Please enter model identifier string" }]}
          >
            <Input placeholder="e.g. gpt-4o-mini or meta/llama-3.3-70b-instruct" />
          </Form.Item>
          <Form.Item
            name="purposes"
            label={<span style={{ color: "var(--text-secondary)" }}>Capabilities / Workloads</span>}
            rules={[{ required: true, message: "Please select at least one capability" }]}
          >
            <Select mode="multiple" placeholder="Select capabilities">
              <Option value="sql_generation">SQL Generation (NL → SQL)</Option>
              <Option value="insight">Business Insight & Summary</Option>
              <Option value="intent">Intent Classification</Option>
              <Option value="chart">Chart / Visualization</Option>
            </Select>
          </Form.Item>
          <Form.Item style={{ margin: 0, marginTop: "24px", textAlign: "right" }}>
            <Space>
              <Button onClick={() => setModelModalVisible(false)}>Cancel</Button>
              <Button type="primary" htmlType="submit" style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}>
                Register Model
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Save API Key Modal */}
      <Modal
        title={<span style={{ color: "var(--text-main)" }}>Manage API Key</span>}
        open={keyModalVisible}
        onCancel={() => setKeyModalVisible(false)}
        footer={null}
        styles={{ body: { backgroundColor: "var(--bg-card)", padding: "16px 24px" } }}
      >
        {selectedProvider && (
          <Form form={formKey} layout="vertical" onFinish={handleSaveKey}>
            <Text type="secondary" style={{ display: "block", marginBottom: "16px" }}>
              API credentials for <strong>{selectedProvider.provider_name}</strong> will be stored encrypted on the database server.
            </Text>
            <Form.Item
              name="api_key"
              label={<span style={{ color: "var(--text-secondary)" }}>Secret Key Token</span>}
              rules={[{ required: true, message: "Please enter token" }]}
            >
              <Input.Password placeholder="Enter new API key token" />
            </Form.Item>
            <Form.Item style={{ margin: 0, marginTop: "24px", textAlign: "right" }}>
              <Space>
                <Button onClick={() => setKeyModalVisible(false)}>Cancel</Button>
                <Button type="primary" htmlType="submit" style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}>
                  Save Token
                </Button>
              </Space>
            </Form.Item>
          </Form>
        )}
      </Modal>
    </div>
  );
}
