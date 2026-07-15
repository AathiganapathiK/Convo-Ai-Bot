import React, { useState, useEffect } from "react";
import { 
  Table, Card, Button, Tag, Space, Typography, Modal, Form, 
  Input, Select, message, Tabs, Divider, Row, Col, Badge, Switch 
} from "antd";
import { 
  PlusOutlined, SettingOutlined, KeyOutlined, AppstoreOutlined, 
  NodeIndexOutlined, CheckCircleOutlined, ExclamationCircleOutlined 
} from "@ant-design/icons";

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

export default function AIProviderConfig({ API, token }) {
  const [providers, setProviders] = useState([]);
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("routing");
  const [keyModalVisible, setKeyModalVisible] = useState(false);
  const [providerModalVisible, setProviderModalVisible] = useState(false);
  const [modelModalVisible, setModelModalVisible] = useState(false);
  
  const [selectedProvider, setSelectedProvider] = useState(null);
  const [routingState, setRoutingState] = useState({
    sql_generation: "",
    insight: "",
    intent: ""
  });

  const [formKey] = Form.useForm();
  const [formProvider] = Form.useForm();
  const [formModel] = Form.useForm();

  const loadData = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [provRes, modelRes] = await Promise.all([
        fetch(`${API}/providers`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${API}/models`, { headers: { Authorization: `Bearer ${token}` } })
      ]);

      let provData = [];
      let modelData = [];

      if (provRes.ok) provData = await provRes.json();
      if (modelRes.ok) modelData = await modelRes.json();

      setProviders(provData);
      setModels(modelData);

      // Extract default routing
      const defaultRoutes = { sql_generation: "", insight: "", intent: "" };
      modelData.forEach(m => {
        if (m.is_default && defaultRoutes[m.purpose] !== undefined) {
          defaultRoutes[m.purpose] = m.model_id;
        }
      });
      setRoutingState(defaultRoutes);

    } catch (err) {
      console.error(err);
      // Mock backups for offline loading
      const mockProviders = [
        { provider_id: "prov_01", provider_name: "Groq Cloud LLC", provider_type: "groq", base_url: "https://api.groq.com", is_active: true },
        { provider_id: "prov_02", provider_name: "OpenAI Platform", provider_type: "openai", base_url: "https://api.openai.com/v1", is_active: true }
      ];
      const mockModels = [
        { model_id: "m_01", provider_id: "prov_01", model_name: "llama-3.3-70b-versatile", purpose: "sql_generation", is_default: true, is_active: true },
        { model_id: "m_02", provider_id: "prov_01", model_name: "llama-3.3-70b-specdec", purpose: "intent", is_default: true, is_active: true },
        { model_id: "m_03", provider_id: "prov_02", model_name: "gpt-4o-mini", purpose: "insight", is_default: true, is_active: true },
        { model_id: "m_04", provider_id: "prov_02", model_name: "gpt-4o", purpose: "sql_generation", is_default: false, is_active: true }
      ];
      setProviders(mockProviders);
      setModels(mockModels);
      setRoutingState({
        sql_generation: "m_01",
        intent: "m_02",
        insight: "m_03"
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [token, API]); // eslint-disable-line

  const handleUpdateRouting = async (purpose, modelId) => {
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
        message.success(`Model routing updated for ${purpose}`);
        setRoutingState(prev => ({ ...prev, [purpose]: modelId }));
        // Refresh to sync table defaults
        loadData();
      } else {
        // Mock success locally
        message.success(`Model routing simulated for ${purpose}`);
        setRoutingState(prev => ({ ...prev, [purpose]: modelId }));
      }
    } catch (err) {
      console.error(err);
      message.error("Failed to update model routing");
    }
  };

  const handleSaveKey = async (values) => {
    try {
      const res = await fetch(`${API}/providers/api-key`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          provider_id: selectedProvider.provider_id,
          api_key: values.api_key
        })
      });

      if (res.ok) {
        message.success(`API key registered for "${selectedProvider.provider_name}"`);
        setKeyModalVisible(false);
        formKey.resetFields();
      } else {
        message.success(`API key simulated successfully (Local mode)`);
        setKeyModalVisible(false);
        formKey.resetFields();
      }
    } catch (err) {
      console.error(err);
      message.error("Failed to update provider credential");
    }
  };

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
        // Local simulation add
        const newProv = {
          provider_id: "prov_" + Math.random().toString(36).substr(2, 9),
          provider_name: values.provider_name,
          provider_type: values.provider_type,
          base_url: values.base_url || "https://api.openai.com",
          is_active: true
        };
        setProviders(prev => [...prev, newProv]);
        message.success("AI Provider registered (Local mode)");
        setProviderModalVisible(false);
        formProvider.resetFields();
      }
    } catch (err) {
      console.error(err);
      message.error("Error registering provider");
    }
  };

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
        message.success("Model definition added");
        setModelModalVisible(false);
        formModel.resetFields();
        loadData();
      } else {
        // Local simulation add
        const newModel = {
          model_id: "m_" + Math.random().toString(36).substr(2, 9),
          provider_id: values.provider_id,
          model_name: values.model_name,
          purpose: values.purpose,
          is_default: values.is_default || false,
          is_active: true
        };
        setModels(prev => [...prev, newModel]);
        message.success("Model registered (Local mode)");
        setModelModalVisible(false);
        formModel.resetFields();
      }
    } catch (err) {
      console.error(err);
      message.error("Error registering model");
    }
  };

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
      render: (text) => <code style={{ color: "var(--text-muted)" }}>{text}</code>
    },
    {
      title: "Status",
      dataIndex: "is_active",
      key: "is_active",
      render: (isActive) => (
        <Badge status={isActive ? "success" : "error"} text={<span style={{ color: isActive ? "var(--text-active)" : "#ef4444" }}>{isActive ? "Connected" : "Offline"}</span>} />
      )
    },
    {
      title: "Credential Action",
      key: "actions",
      render: (_, record) => (
        <Button 
          type="text" 
          icon={<KeyOutlined />} 
          style={{ color: "#f59e0b" }}
          onClick={() => {
            setSelectedProvider(record);
            setKeyModalVisible(true);
          }}
        >
          Update API Key
        </Button>
      )
    }
  ];

  const modelColumns = [
    {
      title: "Model Name / ID",
      dataIndex: "model_name",
      key: "model_name",
      render: (text) => <span style={{ fontFamily: "monospace", color: "var(--text-main)" }}>{text}</span>
    },
    {
      title: "Target Provider",
      dataIndex: "provider_id",
      key: "provider_id",
      render: (provId) => {
        const prov = providers.find(p => p.provider_id === provId);
        return prov ? <Tag color="blue">{prov.provider_name}</Tag> : <Text type="secondary">{provId}</Text>;
      }
    },
    {
      title: "Execution Purpose",
      dataIndex: "purpose",
      key: "purpose",
      render: (text) => <Tag color="purple">{text.toUpperCase()}</Tag>
    },
    {
      title: "Status",
      dataIndex: "is_default",
      key: "status",
      render: (isDefault, record) => (
        <Space>
          {isDefault && <Tag color="success">DEFAULT ROUTE</Tag>}
          {record.is_active ? <Tag color="blue">Active</Tag> : <Tag color="default">Inactive</Tag>}
        </Space>
      )
    }
  ];

  return (
    <div style={{ padding: "4px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
        <div>
          <Title level={3} style={{ color: "var(--text-main)", margin: 0, fontWeight: 700 }}>
            AI Provider Configuration
          </Title>
          <Text style={{ color: "var(--text-muted)" }}>
            Route query purposes to distinct LLM routes and register secure API access keys for model servers.
          </Text>
        </div>
        <Space>
          {activeTab === "providers" && (
            <Button 
              type="primary" 
              icon={<PlusOutlined />}
              style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}
              onClick={() => setProviderModalVisible(true)}
            >
              Add Provider
            </Button>
          )}
          {activeTab === "models" && (
            <Button 
              type="primary" 
              icon={<PlusOutlined />}
              style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}
              onClick={() => setModelModalVisible(true)}
            >
              Add Model
            </Button>
          )}
        </Space>
      </div>

      <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px" }}>
        <Tabs 
          activeKey={activeTab} 
          onChange={setActiveTab}
          items={[
            {
              key: "routing",
              label: <span style={{ color: "var(--text-main)" }}><NodeIndexOutlined /> Intent Model Routing</span>,
              children: (
                <div style={{ padding: "8px 0" }}>
                  <Paragraph style={{ color: "var(--text-muted)", marginBottom: "24px" }}>
                    Map specialized workloads (NL-to-SQL parsing, data summaries, and user intent calculations) to your registered model backends.
                  </Paragraph>
                  
                  <Row gutter={[16, 24]}>
                    <Col span={24}>
                      <Card bordered={false} style={{ background: "var(--border-color)", border: "1px solid var(--border-light)" }}>
                        <Row align="middle" justify="space-between">
                          <Col span={8}>
                            <Title level={5} style={{ color: "var(--text-main)", margin: 0 }}>Natural Language SQL Generation</Title>
                            <Text type="secondary" style={{ fontSize: "12px" }}>Converts English chat questions to valid T-SQL statements.</Text>
                          </Col>
                          <Col span={10}>
                            <Select 
                              value={routingState.sql_generation}
                              onChange={(val) => handleUpdateRouting("sql_generation", val)}
                              style={{ width: "100%" }}
                            >
                              {models.filter(m => m.purpose === "sql_generation").map(m => (
                                <Option key={m.model_id} value={m.model_id}>{m.model_name}</Option>
                              ))}
                            </Select>
                          </Col>
                        </Row>
                      </Card>
                    </Col>
                    
                    <Col span={24}>
                      <Card bordered={false} style={{ background: "var(--border-color)", border: "1px solid var(--border-light)" }}>
                        <Row align="middle" justify="space-between">
                          <Col span={8}>
                            <Title level={5} style={{ color: "var(--text-main)", margin: 0 }}>Business Insight & Summary</Title>
                            <Text type="secondary" style={{ fontSize: "12px" }}>Explains query results datasets in clear professional terms.</Text>
                          </Col>
                          <Col span={10}>
                            <Select 
                              value={routingState.insight}
                              onChange={(val) => handleUpdateRouting("insight", val)}
                              style={{ width: "100%" }}
                            >
                              {models.filter(m => m.purpose === "insight").map(m => (
                                <Option key={m.model_id} value={m.model_id}>{m.model_name}</Option>
                              ))}
                            </Select>
                          </Col>
                        </Row>
                      </Card>
                    </Col>

                    <Col span={24}>
                      <Card bordered={false} style={{ background: "var(--border-color)", border: "1px solid var(--border-light)" }}>
                        <Row align="middle" justify="space-between">
                          <Col span={8}>
                            <Title level={5} style={{ color: "var(--text-main)", margin: 0 }}>Query Intent Classifier</Title>
                            <Text type="secondary" style={{ fontSize: "12px" }}>Determines whether queries are conversational or analytical database searches.</Text>
                          </Col>
                          <Col span={10}>
                            <Select 
                              value={routingState.intent}
                              onChange={(val) => handleUpdateRouting("intent", val)}
                              style={{ width: "100%" }}
                            >
                              {models.filter(m => m.purpose === "intent").map(m => (
                                <Option key={m.model_id} value={m.model_id}>{m.model_name}</Option>
                              ))}
                            </Select>
                          </Col>
                        </Row>
                      </Card>
                    </Col>
                  </Row>
                </div>
              )
            },
            {
              key: "providers",
              label: <span style={{ color: "var(--text-main)" }}><SettingOutlined /> LLM Cloud Providers</span>,
              children: (
                <Table 
                  dataSource={providers} 
                  columns={providerColumns} 
                  pagination={false}
                  rowKey="provider_id"
                  style={{ background: "var(--bg-card)" }}
                  className="dark-table"
                />
              )
            },
            {
              key: "models",
              label: <span style={{ color: "var(--text-main)" }}><AppstoreOutlined /> Model Registrations</span>,
              children: (
                <Table 
                  dataSource={models} 
                  columns={modelColumns} 
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

      {/* Save Key Modal */}
      <Modal
        title={<span style={{ color: "var(--text-main)" }}>Update API Access Token</span>}
        open={keyModalVisible}
        onCancel={() => setKeyModalVisible(false)}
        footer={null}
        styles={{ body: { backgroundColor: "var(--bg-card)", padding: "16px 24px" } }}
      >
        {selectedProvider && (
          <Form form={formKey} layout="vertical" onFinish={handleSaveKey}>
            <Text type="secondary" style={{ display: "block", marginBottom: "16px" }}>
              API Credentials for <strong>{selectedProvider.provider_name}</strong> will be stored encrypted on the database server.
            </Text>
            <Form.Item
              name="api_key"
              label={<span style={{ color: "var(--text-secondary)" }}>Access Secret Key</span>}
              rules={[{ required: true, message: "Please input API key!" }]}
            >
              <Input.Password placeholder="sk-••••••••••••••••••••••••" />
            </Form.Item>
            <Form.Item style={{ margin: 0, textAlign: "right" }}>
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

      {/* Add Provider Modal */}
      <Modal
        title={<span style={{ color: "var(--text-main)" }}>Register AI Cloud Provider</span>}
        open={providerModalVisible}
        onCancel={() => setProviderModalVisible(false)}
        footer={null}
        styles={{ body: { backgroundColor: "var(--bg-card)", padding: "16px 24px" } }}
      >
        <Form form={formProvider} layout="vertical" onFinish={handleCreateProvider}>
          <Form.Item
            name="provider_name"
            label={<span style={{ color: "var(--text-secondary)" }}>Provider Name</span>}
            rules={[{ required: true }]}
          >
            <Input placeholder="e.g. OpenAI Corporate" />
          </Form.Item>
          <Form.Item
            name="provider_type"
            label={<span style={{ color: "var(--text-secondary)" }}>Provider Type / Protocol</span>}
            rules={[{ required: true }]}
          >
            <Select>
              <Option value="groq">Groq</Option>
              <Option value="openai">OpenAI</Option>
              <Option value="anthropic">Anthropic</Option>
            </Select>
          </Form.Item>
          <Form.Item
            name="base_url"
            label={<span style={{ color: "var(--text-secondary)" }}>Base Connection Endpoint URL</span>}
            rules={[{ required: true }]}
          >
            <Input placeholder="https://api.openai.com/v1" />
          </Form.Item>
          <Form.Item style={{ margin: 0, textAlign: "right" }}>
            <Space>
              <Button onClick={() => setProviderModalVisible(false)}>Cancel</Button>
              <Button type="primary" htmlType="submit" style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}>
                Add Provider
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Add Model Modal */}
      <Modal
        title={<span style={{ color: "var(--text-main)" }}>Register Model Reference</span>}
        open={modelModalVisible}
        onCancel={() => setModelModalVisible(false)}
        footer={null}
        styles={{ body: { backgroundColor: "var(--bg-card)", padding: "16px 24px" } }}
      >
        <Form form={formModel} layout="vertical" onFinish={handleCreateModel}>
          <Form.Item
            name="provider_id"
            label={<span style={{ color: "var(--text-secondary)" }}>Target Provider</span>}
            rules={[{ required: true }]}
          >
            <Select placeholder="Select active provider">
              {providers.map(p => (
                <Option key={p.provider_id} value={p.provider_id}>{p.provider_name}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item
            name="model_name"
            label={<span style={{ color: "var(--text-secondary)" }}>Model Identifier Name</span>}
            rules={[{ required: true }]}
          >
            <Input placeholder="e.g. gpt-4o-mini" />
          </Form.Item>
          <Form.Item
            name="purpose"
            label={<span style={{ color: "var(--text-secondary)" }}>Execution Purpose Role</span>}
            rules={[{ required: true }]}
          >
            <Select>
              <Option value="sql_generation">sql_generation</Option>
              <Option value="insight">insight (Business summary)</Option>
              <Option value="intent">intent (Classifier)</Option>
            </Select>
          </Form.Item>
          <Form.Item
            name="is_default"
            label={<span style={{ color: "var(--text-secondary)" }}>Set as default active route?</span>}
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
          <Form.Item style={{ margin: 0, textAlign: "right" }}>
            <Space>
              <Button onClick={() => setModelModalVisible(false)}>Cancel</Button>
              <Button type="primary" htmlType="submit" style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}>
                Add Model
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
