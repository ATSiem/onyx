"use client";

import { PopupSpec, usePopup } from "@/components/admin/connectors/Popup";
import { runConnector } from "@/lib/connector";
import { Button } from "@/components/ui/button";
import Text from "@/components/ui/text";
import { mutate } from "swr";
import { buildCCPairInfoUrl } from "./lib";
import { useState } from "react";
import { Modal } from "@/components/Modal";
import { Separator } from "@/components/ui/separator";
import { Callout } from "@/components/ui/callout";
function ReIndexPopup({
  isInvalid,
  connectorId,
  credentialId,
  ccPairId,
  setPopup,
  hide,
}: {
  isInvalid: boolean;
  connectorId: number;
  credentialId: number;
  ccPairId: number;
  setPopup: (popupSpec: PopupSpec | null) => void;
  hide: () => void;
}) {
  async function triggerIndexing(fromBeginning: boolean) {
    const errorMsg = await runConnector(
      connectorId,
      [credentialId],
      fromBeginning
    );
    if (errorMsg) {
      setPopup({
        message: errorMsg,
        type: "error",
      });
    } else {
      setPopup({
        message: "Triggered connector run",
        type: "success",
      });
    }
    mutate(buildCCPairInfoUrl(ccPairId));
  }

  return (
    <Modal title="Run Indexing" onOutsideClick={hide}>
      <div>
        <Button
          variant="submit"
          className="ml-auto"
          onClick={() => {
            triggerIndexing(false);
            hide();
          }}
        >
          Run Update
        </Button>

        <Text className="mt-2">
          This will pull in and index all documents that have changed and/or
          have been added since the last successful indexing run.
        </Text>

        <Separator />

        <Button
          variant="submit"
          className="ml-auto"
          onClick={() => {
            triggerIndexing(true);
            hide();
          }}
        >
          Run Complete Re-Indexing
        </Button>

        <Text className="mt-2">
          This will cause a complete re-indexing of all documents from the
          source.
        </Text>

        <Text className="mt-2">
          <b>NOTE:</b> depending on the number of documents stored in the
          source, this may take a long time.
        </Text>
        {isInvalid && (
          <div className="mt-2">
            <Callout
              type="warning"
              title="Previous Indexing Attempt was Invalid"
            >
              This connector is in an invalid state. Please update the
              credentials or configuration before re-indexing if you haven't
              already done so.
            </Callout>
          </div>
        )}
      </div>
    </Modal>
  );
}

export function ReIndexButton({
  ccPairId,
  connectorId,
  credentialId,
  isDisabled,
  isIndexing,
  isDeleting,
  isInvalid,
}: {
  ccPairId: number;
  connectorId: number;
  credentialId: number;
  isDisabled: boolean;
  isIndexing: boolean;
  isDeleting: boolean;
  isInvalid: boolean;
}) {
  const { popup, setPopup } = usePopup();
  const [reIndexPopupVisible, setReIndexPopupVisible] = useState(false);

  return (
    <>
      {reIndexPopupVisible && (
        <ReIndexPopup
          isInvalid={isInvalid}
          connectorId={connectorId}
          credentialId={credentialId}
          ccPairId={ccPairId}
          setPopup={setPopup}
          hide={() => setReIndexPopupVisible(false)}
        />
      )}
      {popup}
      <Button
        variant="success-reverse"
        className="ml-auto min-w-[100px]"
        onClick={() => {
          setReIndexPopupVisible(true);
        }}
        disabled={isDisabled || isDeleting}
        tooltip={
          isDeleting
            ? "Cannot index while connector is deleting"
            : isIndexing
              ? "Indexing is already in progress"
              : isDisabled
                ? "Connector must be re-enabled before indexing"
                : undefined
        }
      >
        Index
      </Button>
    </>
  );
}
