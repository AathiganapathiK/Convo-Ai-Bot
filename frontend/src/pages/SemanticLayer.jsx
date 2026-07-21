import React, { useState, useEffect } from "react";
import { 
  Table, Card, Button, Tag, Space, Typography, Modal, Form, 
  Input, Select, message, Tabs, Divider, Switch
} from "antd";
import { 
  PlusOutlined, TagsOutlined, CompassOutlined, 
  EditOutlined, DeleteOutlined, SearchOutlined,
  ReloadOutlined, ClearOutlined
} from "@ant-design/icons";

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

export default function SemanticLayer({ API, token, userInfo }) {
  const [metrics, setMetrics] = useState([]);
  const [dimensions, setDimensions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [editingRecord, setEditingRecord] = useState(null);
  const [activeTab, setActiveTab] = useState("metrics");
  const [form] = Form.useForm();

  // Search & Filter States
  const [searchText, setSearchText] = useState("");
  const [sourceFilter, setSourceFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");

  const role = userInfo?.role?.toUpperCase() || "";
  const isAnalyst = role === "ANALYST";

  const loadData = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [metricsRes, dimsRes] = await Promise.all([
        fetch(`${API}/semantic/metrics`, {
          headers: { Authorization: `Bearer ${token}` }
        }),
        fetch(`${API}/semantic/dimensions`, {
          headers: { Authorization: `Bearer ${token}` }
        })
      ]);

      if (metricsRes.status === 400 || dimsRes.status === 400) {
        setMetrics([]);
        setDimensions([]);
        message.warning("Please select a database to view semantic definitions.");
        return;
      }

      if (!metricsRes.ok) {
        throw new Error(`Metrics API returned status ${metricsRes.status}`);
      }

      if (!dimsRes.ok) {
        throw new Error(`Dimensions API returned status ${dimsRes.status}`);
      }

      const metricsData = await metricsRes.json();
      const dimsData = await dimsRes.json();

      // Map metrics directly to UI structure
      setMetrics(metricsData.map(m => ({
        key: m.metric_id,
        metric_id: m.metric_id,
        metric_name: m.metric_name,
        business_name: m.business_name,
        table_name: m.table_name,
        column_name: m.column_name,
        synonyms: m.synonyms,
        aggregation_type: m.aggregation_type || "SUM",
        description: m.description,
        source: m.source,
        is_active: m.is_active
      })));

      // Map dimensions directly to UI structure
      setDimensions(dimsData.map(d => ({
        key: d.dimension_id,
        dimension_id: d.dimension_id,
        dimension_name: d.dimension_name,
        business_name: d.business_name,
        table_name: d.table_name,
        column_name: d.column_name,
        synonyms: d.synonyms,
        description: d.description,
        source: d.source,
        is_active: d.is_active
      })));
    } catch (err) {
      console.error(err);
      message.error(`Error loading semantic definitions: ${err.message || err}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [token, API]); // eslint-disable-line

  // Compute filtered datasets
  const filteredMetrics = metrics.filter(m => {
    const matchesSearch = 
      (m.metric_name || "").toLowerCase().includes(searchText.toLowerCase()) ||
      (m.business_name || "").toLowerCase().includes(searchText.toLowerCase()) ||
      (m.table_name || "").toLowerCase().includes(searchText.toLowerCase()) ||
      (m.column_name || "").toLowerCase().includes(searchText.toLowerCase()) ||
      (m.description || "").toLowerCase().includes(searchText.toLowerCase());

    const matchesSource = sourceFilter === "ALL" || m.source === sourceFilter;
    const matchesStatus = statusFilter === "ALL" || 
      (statusFilter === "ACTIVE" ? m.is_active : !m.is_active);

    return matchesSearch && matchesSource && matchesStatus;
  });

  const filteredDimensions = dimensions.filter(d => {
    const matchesSearch = 
      (d.dimension_name || "").toLowerCase().includes(searchText.toLowerCase()) ||
      (d.business_name || "").toLowerCase().includes(searchText.toLowerCase()) ||
      (d.table_name || "").toLowerCase().includes(searchText.toLowerCase()) ||
      (d.column_name || "").toLowerCase().includes(searchText.toLowerCase()) ||
      (d.description || "").toLowerCase().includes(searchText.toLowerCase());

    const matchesSource = sourceFilter === "ALL" || d.source === sourceFilter;
    const matchesStatus = statusFilter === "ALL" || 
      (statusFilter === "ACTIVE" ? d.is_active : !d.is_active);

    return matchesSearch && matchesSource && matchesStatus;
  });

  const handleEdit = (record) => {
    setEditingRecord(record);
    setIsModalVisible(true);
    if (record.metric_id !== undefined) {
      form.setFieldsValue({
        business_name: record.business_name,
        metric_name: record.metric_name,
        table_name: record.table_name,
        column_name: record.column_name,
        synonyms: record.synonyms,
        aggregation_type: record.aggregation_type || "SUM",
        description: record.description,
        is_active: record.is_active !== undefined ? record.is_active : true
      });
    } else {
      form.setFieldsValue({
        business_name: record.business_name,
        dimension_name: record.dimension_name,
        table_name: record.table_name,
        column_name: record.column_name,
        synonyms: record.synonyms,
        description: record.description,
        is_active: record.is_active !== undefined ? record.is_active : true
      });
    }
  };

  const handleModalClose = () => {
    setIsModalVisible(false);
    setEditingRecord(null);
    form.resetFields();
  };

  const handleSaveDefinition = async (values) => {
    setModalLoading(true);
    try {
      const isEdit = !!editingRecord;

      if (activeTab === "metrics") {
        const payload = {
          metric_name: values.metric_name,
          business_name: values.business_name,
          description: values.description || "",
          table_name: values.table_name,
          column_name: values.column_name,
          synonyms: values.synonyms,
          aggregation_type: values.aggregation_type,
          is_active: values.is_active !== undefined ? values.is_active : true
        };

        const url = isEdit 
          ? `${API}/semantic/metrics/${editingRecord.metric_id}` 
          : `${API}/semantic/metrics`;
        const method = isEdit ? "PUT" : "POST";

        const res = await fetch(url, {
          method,
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`
          },
          body: JSON.stringify(payload)
        });

        if (res.ok) {
          message.success(`Semantic Metric "${values.business_name}" ${isEdit ? "updated" : "added"} successfully!`);
          handleModalClose();
          loadData();
        } else {
          const errData = await res.json().catch(() => ({}));
          const errMsg = res.status === 409 
            ? "Metric name already exists." 
            : res.status === 403 
            ? "Forbidden: You do not have permission to write to the semantic layer."
            : errData.detail || "Failed to save metric.";
          message.error(errMsg);
        }
      } else {
        const payload = {
          dimension_name: values.dimension_name,
          business_name: values.business_name,
          description: values.description || "",
          table_name: values.table_name,
          column_name: values.column_name,
          synonyms: values.synonyms,
          is_active: values.is_active !== undefined ? values.is_active : true
        };

        const url = isEdit 
          ? `${API}/semantic/dimensions/${editingRecord.dimension_id}` 
          : `${API}/semantic/dimensions`;
        const method = isEdit ? "PUT" : "POST";

        const res = await fetch(url, {
          method,
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`
          },
          body: JSON.stringify(payload)
        });

        if (res.ok) {
          message.success(`Semantic Dimension "${values.business_name}" ${isEdit ? "updated" : "added"} successfully!`);
          handleModalClose();
          loadData();
        } else {
          const errData = await res.json().catch(() => ({}));
          const errMsg = res.status === 409 
            ? "Dimension name already exists." 
            : res.status === 403 
            ? "Forbidden: You do not have permission to write to the semantic layer."
            : errData.detail || "Failed to save dimension.";
          message.error(errMsg);
        }
      }
    } catch (err) {
      console.error(err);
      message.error("Error saving definition");
    } finally {
      setModalLoading(false);
    }
  };

  const handleDelete = (record) => {
    Modal.confirm({
      title: <span style={{ color: "var(--text-main)" }}>Delete Definition</span>,
      content: <span style={{ color: "var(--text-secondary)" }}>Are you sure you want to delete the semantic definition "{record.business_name}"? This action cannot be undone.</span>,
      okText: "Delete",
      okType: "danger",
      cancelText: "Cancel",
      onOk: async () => {
        try {
          const isMetric = record.metric_id !== undefined;
          const url = isMetric 
            ? `${API}/semantic/metrics/${record.metric_id}` 
            : `${API}/semantic/dimensions/${record.dimension_id}`;

          const res = await fetch(url, {
            method: "DELETE",
            headers: { Authorization: `Bearer ${token}` }
          });

          if (res.ok) {
            message.success("Definition removed successfully");
            loadData();
          } else {
            const errData = await res.json().catch(() => ({}));
            const errMsg = res.status === 403
              ? "Forbidden: You do not have permission to perform this action."
              : errData.detail || "Failed to delete definition.";
            message.error(errMsg);
          }
        } catch (err) {
          console.error(err);
          message.error("Error deleting definition");
        }
      }
    });
  };

  const metricColumns = [
    {
      title: "Metric Name",
      dataIndex: "metric_name",
      key: "metric_name",
      sorter: (a, b) => (a.metric_name || "").localeCompare(b.metric_name || ""),
      render: (text) => (
        <span style={{ fontWeight: 600 }}>
          {text}
        </span>
      )
    },
    {
      title: "Business Name",
      dataIndex: "business_name",
      key: "business_name",
      sorter: (a, b) => (a.business_name || "").localeCompare(b.business_name || "")
    },
    {
      title: "Synonyms",
      dataIndex: "synonyms",
      key: "synonyms",
      render: (value) =>
        value || "-"
    },
    {
      title: "Table",
      dataIndex: "table_name",
      key: "table_name",
      sorter: (a, b) => (a.table_name || "").localeCompare(b.table_name || "")
    },
    {
      title: "Column",
      dataIndex: "column_name",
      key: "column_name",
      sorter: (a, b) => (a.column_name || "").localeCompare(b.column_name || "")
    },
    {
      title: "Aggregation",
      dataIndex: "aggregation_type",
      key: "aggregation_type",
      sorter: (a, b) => (a.aggregation_type || "").localeCompare(b.aggregation_type || ""),
      render: (value) => (
        <Tag color="processing">
          {value}
        </Tag>
      )
    },
    {
      title: "Source",
      dataIndex: "source",
      key: "source",
      sorter: (a, b) => (a.source || "").localeCompare(b.source || ""),
      render: (value) => (
        <Tag color={value === "AUTO" ? "blue" : "green"}>
          {value}
        </Tag>
      )
    },
    {
      title: "Status",
      dataIndex: "is_active",
      key: "is_active",
      sorter: (a, b) => (a.is_active === b.is_active ? 0 : a.is_active ? 1 : -1),
      render: (value) => (
        <Tag color={value ? "green" : "red"}>
          {value ? "Active" : "Inactive"}
        </Tag>
      )
    },
    {
      title: "Description",
      dataIndex: "description",
      key: "description"
    },
    {
      title: "Actions",
      key: "actions",
      render: (_, record) => (
        <Space>
          <Button
            type="text"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          />
          <Button
            type="text"
            danger
            disabled={record.source === "AUTO"}
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record)}
          />
        </Space>
      )
    }
  ];


  const dimensionColumns = [
    {
      title: "Dimension Name",
      dataIndex: "dimension_name",
      key: "dimension_name",
      sorter: (a, b) => (a.dimension_name || "").localeCompare(b.dimension_name || ""),
      render: (text) => (
        <span style={{ fontWeight: 600 }}>
          {text}
        </span>
      )
    },
    {
      title: "Business Name",
      dataIndex: "business_name",
      key: "business_name",
      sorter: (a, b) => (a.business_name || "").localeCompare(b.business_name || "")
    },
    {
      title: "Synonyms",
      dataIndex: "synonyms",
      key: "synonyms",
      render: (value) =>
        value || "-"
    },
    {
      title: "Table",
      dataIndex: "table_name",
      key: "table_name",
      sorter: (a, b) => (a.table_name || "").localeCompare(b.table_name || "")
    },
    {
      title: "Column",
      dataIndex: "column_name",
      key: "column_name",
      sorter: (a, b) => (a.column_name || "").localeCompare(b.column_name || "")
    },
    {
      title: "Source",
      dataIndex: "source",
      key: "source",
      sorter: (a, b) => (a.source || "").localeCompare(b.source || ""),
      render: (value) => (
        <Tag color={value === "AUTO" ? "blue" : "green"}>
          {value}
        </Tag>
      )
    },
    {
      title: "Status",
      dataIndex: "is_active",
      key: "is_active",
      sorter: (a, b) => (a.is_active === b.is_active ? 0 : a.is_active ? 1 : -1),
      render: (value) => (
        <Tag color={value ? "green" : "red"}>
          {value ? "Active" : "Inactive"}
        </Tag>
      )
    },
    {
      title: "Description",
      dataIndex: "description",
      key: "description"
    },
    {
      title: "Actions",
      key: "actions",
      render: (_, record) => (
        <Space>
          <Button
            type="text"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          />
          <Button
            type="text"
            danger
            disabled={record.source === "AUTO"}
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record)}
          />
        </Space>
      )
    }
  ];

  return (
    <div style={{ padding: "4px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
        <div>
          <Title level={3} style={{ color: "var(--text-main)", margin: 0, fontWeight: 700 }}>
            Semantic Layer Mappings
          </Title>
          <Text style={{ color: "var(--text-muted)" }}>
            Add synonyms, calculated metrics, and context hints to align the text-to-SQL logic with your business metrics.
          </Text>
        </div>
        {!isAnalyst && (
          <Button 
            type="primary" 
            icon={<PlusOutlined />}
            style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}
            onClick={() => {
              setEditingRecord(null);
              form.resetFields();
              setIsModalVisible(true);
            }}
          >
            Add Definition
          </Button>
        )}
      </div>

      {/* Search and Filters Toolbar */}
      <div style={{ 
        display: "flex", 
        flexWrap: "wrap", 
        gap: "16px", 
        alignItems: "center", 
        justifyContent: "space-between", 
        marginBottom: "20px",
        padding: "16px",
        background: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderRadius: "12px"
      }}>
        <Space wrap size="middle">
          <Input
            placeholder="Search name, table, column..."
            prefix={<SearchOutlined style={{ color: "var(--text-muted)" }} />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 280 }}
            allowClear
          />
          <Select
            placeholder="Source"
            value={sourceFilter}
            onChange={setSourceFilter}
            style={{ width: 140 }}
          >
            <Option value="ALL">All Sources</Option>
            <Option value="AUTO">AUTO</Option>
            <Option value="MANUAL">MANUAL</Option>
          </Select>
          <Select
            placeholder="Status"
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 140 }}
          >
            <Option value="ALL">All Statuses</Option>
            <Option value="ACTIVE">Active</Option>
            <Option value="INACTIVE">Inactive</Option>
          </Select>
          {(searchText || sourceFilter !== "ALL" || statusFilter !== "ALL") && (
            <Button 
              type="link" 
              icon={<ClearOutlined />} 
              onClick={() => {
                setSearchText("");
                setSourceFilter("ALL");
                setStatusFilter("ALL");
              }}
              style={{ color: "#4f46e5" }}
            >
              Clear Filters
            </Button>
          )}
        </Space>
        
        <Button
          icon={<ReloadOutlined />}
          onClick={loadData}
          loading={loading}
        >
          Refresh
        </Button>
      </div>

      <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px" }}>
        <Tabs 
          activeKey={activeTab} 
          onChange={setActiveTab}
          items={[
            {
              key: "metrics",
              label: <span style={{ color: "var(--text-main)" }}><TagsOutlined /> Aggregation Metrics</span>,
              children: (
                <Table 
                  dataSource={filteredMetrics} 
                  columns={isAnalyst ? metricColumns.filter(c => c.key !== "actions") : metricColumns} 
                  pagination={{
                    pageSize: 10,
                    showSizeChanger: true,
                    showTotal: (total) => `Total ${total} items`
                  }}
                  loading={loading}
                  style={{ background: "var(--bg-card)" }}
                  className="dark-table"
                  locale={{ 
                    emptyText: <div style={{ padding: "24px", color: "var(--text-secondary)" }}>No semantic definitions found matching your criteria.</div> 
                  }}
                />
              )
            },
            {
              key: "dimensions",
              label: <span style={{ color: "var(--text-main)" }}><CompassOutlined /> Dimensions & Joins</span>,
              children: (
                <Table 
                  dataSource={filteredDimensions} 
                  columns={isAnalyst ? dimensionColumns.filter(c => c.key !== "actions") : dimensionColumns} 
                  pagination={{
                    pageSize: 10,
                    showSizeChanger: true,
                    showTotal: (total) => `Total ${total} items`
                  }}
                  loading={loading}
                  style={{ background: "var(--bg-card)" }}
                  className="dark-table"
                  locale={{ 
                    emptyText: <div style={{ padding: "24px", color: "var(--text-secondary)" }}>No semantic definitions found matching your criteria.</div> 
                  }}
                />
              )
            }
          ]}
        />
      </Card>

      {/* Definition creation Modal */}
      <Modal
        title={<span style={{ color: "var(--text-main)" }}>{editingRecord ? "Edit Semantic Definition" : "Add Semantic Definition"}</span>}
        open={isModalVisible}
        onCancel={handleModalClose}
        footer={null}
        styles={{ body: { backgroundColor: "var(--bg-card)", padding: "16px 24px" } }}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSaveDefinition}
          initialValues={{ is_active: true, aggregation_type: "SUM" }}
        >
          {activeTab === "metrics" ? (
            <>
              <Form.Item
                name="business_name"
                label={<span style={{ color: "var(--text-secondary)" }}>Metric Name</span>}
                rules={[{ required: true, message: "Please input the metric name!" }]}
              >
                <Input placeholder="e.g. Sales Margin Rate" />
              </Form.Item>

              <Form.Item
                  name="synonyms"
                  label="Synonyms"
              >
                  <Input.TextArea
                      rows={2}
                      placeholder="Customer, Buyer, Dealer, Client"
                  />
              </Form.Item>

              <Form.Item
                name="metric_name"
                label={<span style={{ color: "var(--text-secondary)" }}>Technical Name</span>}
                rules={[{ required: true, message: "Please input the technical name!" }]}
              >
                <Input placeholder="e.g. sales_margin_rate" />
              </Form.Item>

              <Form.Item
                name="table_name"
                label={<span style={{ color: "var(--text-secondary)" }}>Table</span>}
                rules={[{ required: true, message: "Please enter the table name!" }]}
              >
                <Input placeholder="e.g. Sales" />
              </Form.Item>

              <Form.Item
                name="column_name"
                label={<span style={{ color: "var(--text-secondary)" }}>Column</span>}
                rules={[{ required: true, message: "Please input the column name!" }]}
              >
                <Input placeholder="e.g. margin_amount" />
              </Form.Item>

              <Form.Item
                name="aggregation_type"
                label={<span style={{ color: "var(--text-secondary)" }}>Aggregation Type</span>}
                rules={[{ required: true, message: "Please select an aggregation type!" }]}
              >
                <Select placeholder="Select aggregation type">
                  <Option value="SUM">SUM</Option>
                  <Option value="AVG">AVG</Option>
                  <Option value="COUNT">COUNT</Option>
                  <Option value="MIN">MIN</Option>
                  <Option value="MAX">MAX</Option>
                </Select>
              </Form.Item>

              <Form.Item
                name="description"
                label={<span style={{ color: "var(--text-secondary)" }}>Description</span>}
              >
                <Input.TextArea placeholder="Context description for this metric." rows={2} />
              </Form.Item>

              <Form.Item
                name="is_active"
                label={<span style={{ color: "var(--text-secondary)" }}>Active</span>}
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
            </>
          ) : (
            <>
              <Form.Item
                name="dimension_name"
                label={<span style={{ color: "var(--text-secondary)" }}>Dimension Name</span>}
                rules={[{ required: true, message: "Please input the dimension name!" }]}
              >
                <Input placeholder="e.g. Department Branch" />
              </Form.Item>

              <Form.Item
                name="business_name"
                label={<span style={{ color: "var(--text-secondary)" }}>Business Name</span>}
                rules={[{ required: true, message: "Please input the business name!" }]}
              >
                <Input placeholder="e.g. Sales Channel" />
              </Form.Item>

              <Form.Item
                  name="synonyms"
                  label="Synonyms"
              >
                  <Input.TextArea
                      rows={2}
                      placeholder="party,customer,buyer"
                  />
              </Form.Item>

              <Form.Item
                name="table_name"
                label={<span style={{ color: "var(--text-secondary)" }}>Table</span>}
                rules={[{ required: true, message: "Please enter the table name!" }]}
              >
                <Input placeholder="e.g. Sales" />
              </Form.Item>

              <Form.Item
                name="column_name"
                label={<span style={{ color: "var(--text-secondary)" }}>Column</span>}
                rules={[{ required: true, message: "Please input the column name!" }]}
              >
                <Input placeholder="e.g. branch_id" />
              </Form.Item>

              <Form.Item
                name="description"
                label={<span style={{ color: "var(--text-secondary)" }}>Description</span>}
              >
                <Input.TextArea placeholder="Context description for this dimension." rows={2} />
              </Form.Item>

              <Form.Item
                name="is_active"
                label={<span style={{ color: "var(--text-secondary)" }}>Active</span>}
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
            </>
          )}

          <Divider style={{ borderColor: "var(--border-color)", margin: "16px 0" }} />

          <Form.Item style={{ margin: 0, textAlign: "right" }}>
            <Space>
              <Button onClick={handleModalClose} disabled={modalLoading}>
                Cancel
              </Button>
              <Button type="primary" htmlType="submit" loading={modalLoading} style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}>
                Save Definition
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
