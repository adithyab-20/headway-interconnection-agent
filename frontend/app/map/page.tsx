import type { Metadata } from "next";
import { MapApp } from "@/components/map/MapApp";
import { PageTransition } from "@/components/PageTransition";

export const metadata: Metadata = { title: "Map" };

export default function MapPage() {
  return (
    <PageTransition>
      <MapApp />
    </PageTransition>
  );
}
