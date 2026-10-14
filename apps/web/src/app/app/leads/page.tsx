"use client";
import { Suspense } from "react";
import { CaptureButton } from "@/components/ai/capture-dialog";
import { EntityList } from "@/components/list/entity-list";
import { LEADS } from "@/lib/entities";

export default function Page() { return <Suspense><EntityList cfg={LEADS} actions={<CaptureButton />} /></Suspense>; }
