"use client";

import { useState } from "react";
import Button from "@/components/atoms/Button";
import TextArea from "@/components/atoms/TextArea";
import TextField from "@/components/atoms/TextField";
import Modal from "@/components/molecules/Modal";
import SectionLayout from "@/components/molecules/SectionLayout";
import SectionTitle from "@/components/molecules/SectionTitle";
import ConfiguredPageHeader from "@/components/organisms/ConfiguredPageHeader";
import AppLayout from "@/components/templates/AppLayout";

export default function ProductAddPage() {
  const [visible, setVisible] = useState(false);

  return (
    <AppLayout pageHeader={<ConfiguredPageHeader pageKey="productAdd" />}>
      <section className="detail-page-popup-preview">
        <Button
          buttonType="primary"
          size="large"
          stylingMode="contained"
          text="새 상품 추가 모달 열기"
          visualType="default"
          onClick={() => setVisible(true)}
        />
      </section>

      <Modal
        actions={[
          {
            buttonType: "negative",
            key: "cancel",
            onClick: () => setVisible(false),
            stylingMode: "contained",
            text: "취소",
          },
          {
            buttonType: "primary",
            key: "save",
            onClick: () => setVisible(false),
            stylingMode: "contained",
            text: "저장",
            visualType: "default",
          },
        ]}
        modalSize="common"
        title="새 상품 추가"
        visible={visible}
        onClose={() => setVisible(false)}
      >
        <SectionLayout as="section" gap={8}>
          <SectionTitle as="h3" required size="small" title="상품명" />
          <div className="common-table01">
            <TextField width="calc(100% - 109px)" />
            <Button
              buttonType="secondary"
              disabled
              size="medium"
              stylingMode="outlined"
              text="중복확인"
            />
          </div>
        </SectionLayout>

        <SectionLayout as="section" gap={8}>
          <SectionTitle as="h3" size="small" title="상품 설명" />
          <TextField width="100%" />
        </SectionLayout>

        <SectionLayout as="section" gap={8}>
          <SectionTitle as="h3" size="small" title="메모" />
          <TextArea height={128} />
        </SectionLayout>
      </Modal>
    </AppLayout>
  );
}
