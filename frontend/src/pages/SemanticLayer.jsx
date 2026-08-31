import React, { useState } from "react";
import {
  Card, Button, Space, Typography, Modal, Tabs, Descriptions, Alert
} from "antd";
import { message } from "../utils/message";
import { modal } from "../utils/modal";
import {
  TagsOutlined, SyncOutlined, SafetyCertificateOutlined,
  ThunderboltOutlined, ApartmentOutlined, FieldTimeOutlined
} from "@ant-design/icons";

import ColumnsWorkbench from "../components/semanticConfig/ColumnsWorkbench";
import DomainsPanel from "../components/semanticConfig/DomainsPanel";
import TableConfigPanel from "../components/semanticConfig/TableConfigPanel";

const { Title, Text } = Typography;

// Gate 2 - the semantic layer is three unified areas: Columns (the workbench
// that merged the old Metrics / Dimensions / Suggestions tabs, and now owns
// manual definition creation), Domains, and Tables & Temporal. Metrics and
// dimensions are no longer listed here directly; ColumnsWorkbench loads and
// refreshes its own data.
export default function SemanticLayer({ API, token, userInfo }) {
  const [activeTab, setActiveTab] = useState("columns");

  const [indexVerifyOpen, setIndexVerifyOpen] = useState(false);
  const [indexStatus, setIndexStatus] = useState(null);
  const [indexVerifyLoading, setIndexVerifyLoading] = useState(false);
  const [indexRebuildLoading, setIndexRebuildLoading] = useState(false);
  const [discoveryLoading, setDiscoveryLoading] = useState(false);

  // Bumped after a discovery run so the Columns workbench reloads. This
  // replaces the page-level loadData() that discovery used to call back into.
  const [reloadSignal, setReloadSignal] = useState(0);

  const role = userInfo?.role?.toUpperCase() || "";
  const isAnalyst = role === "ANALYST";

  const handleVerifyDimensionIndex = async () => {
    if (!token) return;
    setIndexVerifyLoading(true);
    setIndexStatus(null);
    setIndexVerifyOpen(true);
    try {
      const res = await fetch(`${API}/semantic/dimension-value-index/status`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.status === 400) {
        message.warning("Please configure an active database connection first.");
        setIndexVerifyOpen(false);
        return;
      }
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Status check failed (${res.status})`);
      }
      const data = await res.json();
      setIndexStatus(data);
    } catch (err) {
      console.error(err);
      message.error(err.message || "Could not verify dimension value index.");
      setIndexVerifyOpen(false);
    } finally {
      setIndexVerifyLoading(false);
    }
  };

  const handleRebuildDimensionIndex = async () => {
    if (!token) return;
    setIndexRebuildLoading(true);
    try {
      const res = await fetch(`${API}/semantic/dimension-value-index/rebuild`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Rebuild failed");
      }
      const data = await res.json();
      const summary = data.result || {};
      message.success(
        `Index rebuilt: ${summary.indexed ?? 0} indexed, ` +
        `${summary.skipped ?? 0} skipped, ${summary.failed ?? 0} failed.`
      );
      setIndexVerifyOpen(false);
      await handleVerifyDimensionIndex();
    } catch (err) {
      console.error(err);
      message.error(err.message || "Dimension value index rebuild failed.");
    } finally {
      setIndexRebuildLoading(false);
    }
  };

  const confirmRebuildDimensionIndex = () => {
    modal.confirm({
      title: "Rebuild dimension value index?",
      content: (
        <span>
          This rescans distinct values for all active dimensions on the current connection.
          Raw date and datetime columns are skipped; year and month dimensions use extracted values.
          This may take several minutes on large databases.
        </span>
      ),
      okText: "Rebuild index",
      cancelText: "Cancel",
      okButtonProps: { loading: indexRebuildLoading },
      onOk: () => handleRebuildDimensionIndex()
    });
  };

  const handleRunSemanticDiscovery = () => {
    modal.confirm({
      title: "Run full semantic discovery?",
      content: (
        <span>
          This refreshes auto-discovered metrics and dimensions from the synced schema,
          then rebuilds the dimension value index. Manual synonyms and categories you kept
          are preserved where discovery supports it. Use this instead of disabling and
          re-enabling the datasource.
        </span>
      ),
      okText: "Run discovery",
      cancelText: "Cancel",
      onOk: async () => {
        setDiscoveryLoading(true);
        try {
          const res = await fetch(`${API}/semantic/discover`, {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` }
          });
          if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || "Semantic discovery failed");
          }
          message.success("Semantic discovery completed successfully.");
          setReloadSignal((n) => n + 1);
        } catch (err) {
          console.error(err);
          message.error(err.message || "Semantic discovery failed.");
          throw err;
        } finally {
          setDiscoveryLoading(false);
        }
      }
    });
  };

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
          <Space wrap>
            <Button
              icon={<SafetyCertificateOutlined />}
              onClick={handleVerifyDimensionIndex}
              loading={indexVerifyLoading}
            >
              Verify index
            </Button>
            <Button
              icon={<SyncOutlined />}
              onClick={confirmRebuildDimensionIndex}
              loading={indexRebuildLoading}
            >
              Rebuild value index
            </Button>
            <Button
              icon={<ThunderboltOutlined />}
              onClick={handleRunSemanticDiscovery}
              loading={discoveryLoading}
            >
              Run semantic discovery
            </Button>
          </Space>
        )}
      </div>

      <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px" }}>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: "columns",
              label: (
                <span style={{ color: "var(--text-main)" }}>
                  <TagsOutlined /> Columns
                </span>
              ),
              children: (
                <ColumnsWorkbench
                  API={API}
                  token={token}
                  canEdit={!isAnalyst}
                  reloadSignal={reloadSignal}
                />
              )
            },
            {
              key: "domains",
              label: (
                <span style={{ color: "var(--text-main)" }}>
                  <ApartmentOutlined /> Domains
                </span>
              ),
              children: (
                <DomainsPanel
                  API={API}
                  token={token}
                  canEdit={!isAnalyst}
                />
              )
            },
            {
              key: "tables",
              label: (
                <span style={{ color: "var(--text-main)" }}>
                  <FieldTimeOutlined /> Tables &amp; Temporal
                </span>
              ),
              children: (
                <TableConfigPanel
                  API={API}
                  token={token}
                  canEdit={!isAnalyst}
                />
              )
            }
          ]}
        />
      </Card>

      <Modal
        title={<span style={{ color: "var(--text-main)" }}>Dimension value index</span>}
        open={indexVerifyOpen}
        onCancel={() => {
          setIndexVerifyOpen(false);
          setIndexStatus(null);
        }}
        footer={[
          <Button key="close" onClick={() => setIndexVerifyOpen(false)}>
            Close
          </Button>,
          !isAnalyst && (
            <Button
              key="rebuild"
              type="primary"
              icon={<SyncOutlined />}
              loading={indexRebuildLoading}
              onClick={confirmRebuildDimensionIndex}
              style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}
            >
              Rebuild index
            </Button>
          )
        ].filter(Boolean)}
        styles={{ body: { backgroundColor: "var(--bg-card)" } }}
      >
        {indexVerifyLoading ? (
          <div style={{ padding: "24px", textAlign: "center", color: "var(--text-muted)" }}>
            Loading index status…
          </div>
        ) : indexStatus ? (
          <>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              message="Index verification"
              description="Compare active dimensions with indexed value rows. If counts look stale after schema changes, run Rebuild value index or full semantic discovery."
            />
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="Active dimensions">
                {indexStatus.active_dimensions}
              </Descriptions.Item>
              <Descriptions.Item label="Dimensions with indexed values">
                {indexStatus.dimensions_with_values}
              </Descriptions.Item>
              <Descriptions.Item label="Total indexed value rows">
                {indexStatus.indexed_value_rows}
              </Descriptions.Item>
            </Descriptions>
          </>
        ) : null}
      </Modal>
    </div>
  );
}
