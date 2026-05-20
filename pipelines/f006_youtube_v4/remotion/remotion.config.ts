// 목적: Remotion 렌더링 설정 - F006 유튜브 파이프라인용
import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("png");
Config.setOverwriteOutput(true);
Config.setCodec("h264");
Config.setOutputLocation("out/");
