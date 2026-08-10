import unittest
from unittest.mock import Mock, patch

import requests

import collector
import fetch_onbid
import onbid_api


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class OnbidApiClientTests(unittest.TestCase):
    def test_next_generation_endpoint_and_nested_response(self):
        response = FakeResponse(
            payload={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "OK"},
                    "body": {"totalCount": 0, "items": []},
                }
            }
        )

        with patch("onbid_api.requests.get", return_value=response) as get:
            body = onbid_api.fetch_page(
                {"serviceKey": "secret", "pvctTrgtYn": "N"},
                "테스트",
                logger=Mock(),
            )

        self.assertEqual(body["totalCount"], 0)
        self.assertEqual(
            get.call_args.args[0],
            "https://apis.data.go.kr/B010003/OnbidRlstListSrvc2/getRlstCltrList2",
        )
        self.assertEqual(get.call_args.kwargs["timeout"], (10, 45))

    def test_timeout_is_retried(self):
        success = FakeResponse(
            payload={
                "header": {"resultCode": "00", "resultMsg": "OK"},
                "body": {"totalCount": 0, "items": {}},
            }
        )
        effects = [requests.exceptions.Timeout(), requests.exceptions.Timeout(), success]

        with patch("onbid_api.requests.get", side_effect=effects) as get, patch(
            "onbid_api.time.sleep"
        ) as sleep:
            body = onbid_api.fetch_page({}, "재시도 테스트", logger=Mock())

        self.assertEqual(body["totalCount"], 0)
        self.assertEqual(get.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_http_error_exposes_api_code_but_not_key(self):
        response = FakeResponse(
            status_code=400,
            payload={"header": {"resultCode": "10", "resultMsg": "필수값 누락"}},
        )

        with patch("onbid_api.requests.get", return_value=response):
            with self.assertRaises(onbid_api.OnbidApiError) as caught:
                onbid_api.fetch_page(
                    {"serviceKey": "never-log-this"}, "오류 테스트", logger=Mock()
                )

        message = str(caught.exception)
        self.assertIn("HTTP 400", message)
        self.assertIn("API 10", message)
        self.assertNotIn("never-log-this", message)

    def test_gateway_auth_error_is_summarized(self):
        response = FakeResponse(
            status_code=403,
            payload={
                "OpenAPI_ServiceResponse": {
                    "cmmMsgHeader": {
                        "errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
                        "returnAuthMsg": "등록되지 않은 서비스키",
                        "returnReasonCode": "30",
                    }
                }
            },
        )

        with patch("onbid_api.requests.get", return_value=response):
            with self.assertRaises(onbid_api.OnbidApiError) as caught:
                onbid_api.fetch_page({}, "인증 테스트", logger=Mock())

        self.assertIn("API 30: 등록되지 않은 서비스키", str(caught.exception))

    def test_no_data_code_returns_none(self):
        response = FakeResponse(
            payload={
                "header": {"resultCode": "03", "resultMsg": "NO DATA"},
                "body": {},
            }
        )
        with patch("onbid_api.requests.get", return_value=response):
            self.assertIsNone(onbid_api.fetch_page({}, "데이터 없음", logger=Mock()))


class CollectorIntegrationTests(unittest.TestCase):
    def test_collector_output_keeps_frontend_fields(self):
        raw = {
            "cltrMngNo": "2026-1",
            "pbctCdtnNo": "123",
            "onbidCltrNm": "강원특별자치도 평창군 봉평면 산 1 임야",
            "lctnSdnm": "강원특별자치도",
            "lctnSggnm": "평창군",
            "cltrUsgSclsCtgrNm": "임야",
            "landSqms": "1000",
            "apslEvlAmt": "100000000",
            "lowstBidPrcIndctCont": "50,000,000",
            "usbdNft": "2",
            "cltrBidBgngDt": "20260810000000",
            "cltrBidEndDt": "20260820000000",
            "exctOrgNm": "한국자산관리공사",
            "thnlImgUrlAdr": "https://example.invalid/image.jpg",
            "batcBidYn": "N",
            "pvctTrgtYn": "N",
        }

        item = collector.clean_item(raw)
        required_fields = {
            "cltrNo",
            "cltrNm",
            "addr",
            "sido",
            "sigungu",
            "useNm",
            "area",
            "apprAmt",
            "minBidAmt",
            "apprAmtRaw",
            "minBidAmtRaw",
            "usbdCnt",
            "bidBgDt",
            "bidEdDt",
            "pbctNo",
            "pbctNsq",
            "prptDivNm",
            "orgNm",
            "thumbUrl",
            "onbidUrl",
            "apslPrcRto",
            "batcBidYn",
            "pvctTrgtYn",
            "alcYn",
            "pnu",
            "grade",
        }
        self.assertTrue(required_fields.issubset(item))
        self.assertEqual(item["usbdCnt"], 2)
        self.assertEqual(item["minBidAmtRaw"], 50000000.0)

    def _assert_required_parameter(self, module):
        captured = {}

        def fake_fetch(params, context, logger):
            captured.update(params)
            return None

        with patch.object(module, "fetch_page", side_effect=fake_fetch):
            result = module.fetch_region_prpt("강원특별자치도", "0007", "압류재산", set())

        self.assertEqual(result, [])
        self.assertEqual(captured["pvctTrgtYn"], "N")
        self.assertEqual(captured["prptDivCd"], "0007")
        self.assertEqual(captured["resultType"], "json")

    def test_collector_uses_required_next_generation_parameter(self):
        self._assert_required_parameter(collector)

    def test_fetch_onbid_uses_required_next_generation_parameter(self):
        self._assert_required_parameter(fetch_onbid)

    def test_partial_collection_is_rejected(self):
        with patch.object(collector, "REGIONS", ["강원특별자치도"]), patch.object(
            collector, "PRPT_CODES", [("0007", "압류재산")]
        ), patch.object(collector, "fetch_region_prpt", return_value=None):
            with self.assertRaisesRegex(onbid_api.OnbidApiError, "전체 작업을 중단"):
                collector.fetch_all()

    def test_zero_result_exits_with_failure(self):
        with patch.object(collector, "AUTH_KEY", "configured"), patch.object(
            collector, "fetch_all", return_value=[]
        ), patch.object(collector, "save_json") as save_json, patch.object(
            collector, "save_js"
        ) as save_js:
            result = collector.main()

        self.assertEqual(result, 1)
        save_json.assert_not_called()
        save_js.assert_not_called()


if __name__ == "__main__":
    unittest.main()
