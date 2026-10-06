"use client";
import { Suspense } from "react";
import { EntityList } from "@/components/list/entity-list";
import { COMPANIES } from "@/lib/entities";

export default function Page() { return <Suspense><EntityList cfg={COMPANIES} /></Suspense>; }
