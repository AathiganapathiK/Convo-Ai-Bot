import React, { useState, useEffect } from "react";
import { 
  Row, Col, Card, Tree, Table, Tag, Button, Space, Typography, 
  Tabs, Badge, Tooltip, Input, Alert, message, Spin
} from "antd";
import { 
  SearchOutlined, SyncOutlined, DatabaseOutlined, TableOutlined, 
  KeyOutlined, EyeOutlined, FileTextOutlined, InfoCircleOutlined,
  PartitionOutlined
} from "@ant-design/icons";

const { Title, Text, Paragraph } = Typography;

export default function SchemaDiscovery({ API, token, userInfo }) {
  const [activeConnection, setActiveConnection] = useState(null);
  const [tables, setTables] = useState([]);
  const [selectedTableKey, setSelectedTableKey] = useState(null);
  const [activeTable, setActiveTable] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [scanLoading, setScanLoading] = useState(false);
  const [pageLoading, setPageLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(false);

  const role = userInfo?.role?.toUpperCase() || "";
  const isAnalyst = role === "ANALYST";

  const fetchActiveSchema = async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API}/schema/active`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setActiveConnection(data.active_connection);
        setTables(data.tables || []);
        
        // Select first table if none is selected
        if (data.tables && data.tables.length > 0) {
          setSelectedTableKey(data.tables[0].table_id);
        } else {
          setSelectedTableKey(null);
          setActiveTable(null);
        }
      } else {
        message.error("Failed to load active schema metadata");
      }
    } catch (err) {
      console.error(err);
      message.error("Error fetching schema metadata");
    } finally {
      setPageLoading(false);
    }
  };

  const fetchTableDetails = async (tableId) => {
    if (!token || !tableId) return;
    setTableLoading(true);
    try {
      const res = await fetch(`${API}/schema/tables/${tableId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setActiveTable(data);
      } else {
        message.error("Failed to load table details");
      }
    } catch (err) {
      console.error(err);
      message.error("Error fetching table details");
    } finally {
      setTableLoading(false);
    }
  };

  useEffect(() => {
    fetchActiveSchema();
  }, [token, API]); // eslint-disable-line

  useEffect(() => {
    if (selectedTableKey) {
      fetchTableDetails(selectedTableKey);
    }
  }, [selectedTableKey]); // eslint-disable-line

  const handleTriggerDiscovery = async () => {
    setScanLoading(true);
    try {
      const res = await fetch(`${API}/connections/active/sync`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        message.success("Schema metadata discovery successfully synchronized!");
        await fetchActiveSchema();
      } else {
        const errData = await res.json().catch(() => ({}));
        message.error(errData.detail || "Schema sync failed");
      }
    } catch (err) {
      console.error(err);
      message.error("Schema sync request failed");
    } finally {
      setScanLoading(false);
    }
  };

  // Filter tables based on search query
  const filteredTables = tables.filter(t => 
    t.table_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (t.schema_name && t.schema_name.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  // Tree data structure
  const treeData = activeConnection ? [
    {
      title: activeConnection.database_name,
      key: "db_root",
      icon: <DatabaseOutlined style={{ color: "#6366f1" }} />,
      children: filteredTables.map(t => ({
        title: `${t.schema_name ? t.schema_name + '.' : ''}${t.table_name}`,
        key: t.table_id,
        icon: <TableOutlined style={{ color: "#3b82f6" }} />,
        isLeaf: true
      }))
    }
  ] : [];

  const columnColumns = [
    {
      title: "Column Name",
      dataIndex: "name",
      key: "name",
      render: (text, record) => {
        const isKey = record.constraint.includes("PRIMARY") || record.constraint.includes("FOREIGN");
        return (
          <Space>
            {isKey ? <KeyOutlined style={{ color: "#f59e0b" }} /> : <FileTextOutlined style={{ color: "var(--text-muted)" }} />}
            <span style={{ fontWeight: 600, color: "var(--text-main)" }}>{text}</span>
          </Space>
        );
      }
    },
    {
      title: "Data Type",
      dataIndex: "type",
      key: "type",
      render: (text) => <code style={{ color: "var(--code-purple)" }}>{text}</code>
    },
    {
      title: "Tag / Classification",
      dataIndex: "constraint",
      key: "constraint",
      render: (text) => {
        if (!text || text === "NONE") return <Tag color="default" bordered={false}>NONE</Tag>;
        return (
          <Space size={4}>
            {text.split(",").map(tag => {
              let color = "blue";
              const cleaned = tag.trim();
              if (cleaned.includes("PRIMARY")) color = "gold";
              if (cleaned.includes("FOREIGN")) color = "orange";
              if (cleaned.includes("SENSITIVE")) color = "red";
              if (cleaned.includes("MEASURE")) color = "purple";
              return <Tag key={cleaned} color={color} bordered={false} style={{ textTransform: "uppercase", fontSize: "10px" }}>{cleaned}</Tag>;
            })}
          </Space>
        );
      }
    },
    {
      title: "Nullable",
      dataIndex: "nullable",
      key: "nullable",
      render: (text) => <span style={{ color: text === "YES" ? "#6b7280" : "var(--text-secondary)" }}>{text}</span>
    },
    {
      title: "Description",
      dataIndex: "desc",
      key: "desc",
      render: (text) => <span style={{ color: "var(--text-muted)" }}>{text}</span>
    }
  ];

  // Dynamic sample data columns
  const sampleDataColumns = activeTable && activeTable.sampleData && activeTable.sampleData.length > 0
    ? Object.keys(activeTable.sampleData[0]).map(col => ({
        title: col,
        dataIndex: col,
        key: col,
        render: (val) => {
          if (typeof val === "number") {
            return <span style={{ color: "var(--code-blue)", fontWeight: 500 }}>{val}</span>;
          }
          return <span style={{ color: "var(--text-main)" }}>{val !== null && val !== undefined ? String(val) : <span style={{ color: "#6b7280", fontStyle: "italic" }}>NULL</span>}</span>;
        }
      }))
    : [];

  if (pageLoading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "400px" }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ padding: "4px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
        <div>
          <Title level={3} style={{ color: "var(--text-main)", margin: 0, fontWeight: 700 }}>
            Schema Discovery
          </Title>
          <Text style={{ color: "var(--text-muted)" }}>
            Inspect table structures, primary key references, and catalog index parameters analyzed by the metadata discovery parser.
          </Text>
        </div>
        {!isAnalyst && activeConnection && (
          <Button 
            type="primary" 
            icon={<SyncOutlined spin={scanLoading} />}
            loading={scanLoading}
            style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}
            onClick={handleTriggerDiscovery}
          >
            Scan database
          </Button>
        )}
      </div>

      {!activeConnection ? (
        <Alert
          message="No active database connection. Configure a connection and run schema sync."
          type="warning"
          showIcon
          style={{ borderRadius: "12px", padding: "16px" }}
        />
      ) : (
        <Row gutter={[16, 16]}>
          {/* Left Side: Tables Navigation Tree */}
          <Col xs={24} md={6}>
            <Card 
              title={
                <Input 
                  prefix={<SearchOutlined style={{ color: "#6b7280" }} />} 
                  placeholder="Search tables..." 
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  style={{ background: "var(--border-color)", border: "1px solid var(--border-light)" }}
                />
              }
              bordered={false} 
              style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px", minHeight: "500px" }}
            >
              {treeData.length > 0 && (
                <Tree
                  showIcon
                  defaultExpandAll
                  selectedKeys={selectedTableKey ? [selectedTableKey] : []}
                  onSelect={(keys) => {
                    if (keys[0] && keys[0] !== "db_root") {
                      setSelectedTableKey(keys[0]);
                    }
                  }}
                  treeData={treeData}
                  style={{ background: "transparent", color: "var(--text-secondary)" }}
                  className="dark-tree"
                />
              )}
            </Card>
          </Col>

          {/* Right Side: Column definitions & sample data */}
          <Col xs={24} md={18}>
            {tableLoading ? (
              <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px", minHeight: "300px", display: "flex", justifyContent: "center", alignItems: "center" }}>
                <Spin size="large" />
              </Card>
            ) : activeTable ? (
              <Card 
                title={
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%" }}>
                    <Space size="middle">
                      <span style={{ color: "var(--text-main)", fontSize: "18px", fontWeight: 700 }}>
                        {activeTable.name}
                      </span>
                      <Badge count={`${activeTable.rowCount.toLocaleString()} Rows`} style={{ backgroundColor: "var(--bg-selected-chat)", border: "1px solid var(--border-color)", color: "var(--text-main)" }} />
                    </Space>
                    <span style={{ fontSize: "12px", color: "#6b7280" }}>
                      Discovered: {activeTable.lastDiscovered}
                    </span>
                  </div>
                }
                bordered={false}
                style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px" }}
              >
                <Paragraph style={{ color: "var(--text-muted)", marginBottom: "20px" }}>
                  {activeTable.description}
                </Paragraph>

                <Tabs 
                  defaultActiveKey="columns"
                  items={[
                    {
                      key: "columns",
                      label: <span style={{ color: "var(--text-main)" }}><InfoCircleOutlined /> Column Definitions</span>,
                      children: (
                        <Table 
                          dataSource={activeTable.columns} 
                          columns={columnColumns} 
                          pagination={false}
                          style={{ background: "var(--bg-card)" }}
                          className="dark-table"
                        />
                      )
                    },
                    {
                      key: "relationships",
                      label: <span style={{ color: "var(--text-main)" }}><PartitionOutlined /> Relationships</span>,
                      children: (
                        <Table 
                          dataSource={activeTable.relationships || []} 
                          columns={[
                            { 
                              title: "Source", 
                              key: "source",
                              render: (_, rec) => (
                                <Space>
                                  <Tag color="blue">{rec.source_table}</Tag>
                                  <code>{rec.source_column}</code>
                                </Space>
                              )
                            },
                            { 
                              title: "Direction", 
                              key: "direction", 
                              render: () => <span style={{ color: "var(--text-muted)" }}>references →</span>
                            },
                            { 
                              title: "Target", 
                              key: "target",
                              render: (_, rec) => (
                                <Space>
                                  <Tag color="purple">{rec.target_table}</Tag>
                                  <code>{rec.target_column}</code>
                                </Space>
                              )
                            }
                          ]} 
                          pagination={false}
                          rowKey="relationship_id"
                          style={{ background: "var(--bg-card)" }}
                          className="dark-table"
                        />
                      )
                    },
                    {
                      key: "sample",
                      label: <span style={{ color: "var(--text-main)" }}><EyeOutlined /> Sample Records</span>,
                      children: (
                        <Table 
                          dataSource={activeTable.sampleData} 
                          columns={sampleDataColumns} 
                          pagination={false}
                          rowKey={(record, idx) => idx}
                          style={{ background: "var(--bg-card)" }}
                          className="dark-table"
                        />
                      )
                    }
                  ]}
                />
              </Card>
            ) : (
              <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px", minHeight: "300px", display: "flex", justifyContent: "center", alignItems: "center" }}>
                <Text style={{ color: "var(--text-muted)" }}>No tables available. Click "Scan database" to synchronize the schema.</Text>
              </Card>
            )}
          </Col>
        </Row>
      )}
    </div>
  );
}
